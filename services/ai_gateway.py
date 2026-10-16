"""Central Gemini gateway with shared Redis cache/rate limiting and safe fallback."""
import hashlib
import json
import os
import time
from pathlib import Path
from threading import Lock
from dotenv import load_dotenv

try:
    from redis import Redis
except Exception:
    Redis = None

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / ".env.local", override=True)

CACHE_DIR = ROOT / "data" / "ai_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
AI_RPM = max(1, int(os.getenv("AI_RPM", "8")))
AI_RATE_LIMIT_FAIL_OPEN = os.getenv("AI_RATE_LIMIT_FAIL_OPEN", "true").strip().lower() in {"1", "true", "yes", "on"}


def _redis_client():
    if Redis is None or not os.getenv("REDIS_URL"):
        return None
    try:
        return Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)
    except Exception:
        return None


REDIS = _redis_client()


def _metric(name: str, amount: int = 1):
    if REDIS is None:
        return
    try:
        REDIS.incrby(f"metrics:{name}", amount)
    except Exception:
        pass


class TokenBucket:
    """Local fallback only; Redis enforces the cross-process request ceiling."""
    def __init__(self, capacity=8, refill_per_minute=8):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.rate = refill_per_minute / 60.0
        self.updated = time.monotonic()
        self.lock = Lock()

    def acquire(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True


def _global_rate_allow(limit: int) -> bool:
    if REDIS is None:
        return AI_RATE_LIMIT_FAIL_OPEN
    try:
        minute = int(time.time() // 60)
        key = f"ai-rate:{minute}"
        value = int(REDIS.eval(
            "local n=redis.call('INCR',KEYS[1]); "
            "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1, key, 90,
        ))
        return value <= limit
    except Exception:
        return AI_RATE_LIMIT_FAIL_OPEN


class AIGateway:
    def __init__(self):
        self.bucket = TokenBucket(AI_RPM, AI_RPM)
        self.failures = 0
        self.open_until = 0.0
        self.api_calls = 0
        self.client = None
        self.init_error = None
        key = os.getenv("GEMINI_API_KEY")
        if key:
            try:
                from google import genai
                from google.genai import types
                self.client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=15000))
            except Exception as exc:
                self.init_error = str(exc)[:200]

    @property
    def available(self):
        return self.client is not None and time.time() >= self.open_until

    def _key(self, prompt, model):
        return hashlib.sha256((model + prompt).encode()).hexdigest()

    def _cache_get(self, key: str, ttl: int):
        if REDIS is not None:
            try:
                raw = REDIS.get(f"ai-cache:{key}")
                if raw:
                    _metric("ai_cache_hit")
                    return raw
            except Exception:
                pass
        path = CACHE_DIR / f"{key}.json"
        if path.exists() and time.time() - path.stat().st_mtime < ttl:
            try:
                _metric("ai_cache_hit")
                return json.loads(path.read_text(encoding="utf-8"))["text"]
            except Exception:
                return None
        return None

    def _cache_put(self, key: str, text: str, ttl: int):
        if REDIS is not None:
            try:
                REDIS.setex(f"ai-cache:{key}", ttl, text)
                return
            except Exception:
                pass
        try:
            (CACHE_DIR / f"{key}.json").write_text(json.dumps({"text": text, "created_at": time.time()}), encoding="utf-8")
        except Exception:
            pass

    def generate(self, prompt, model=None, cache_ttl=604800, retries=2, json_mode=False, temperature=None):
        model = model or DEFAULT_MODEL
        cache_key_prompt = f"json={bool(json_mode)}|temp={temperature}|{prompt}"
        key = self._key(cache_key_prompt, model)
        cached = self._cache_get(key, cache_ttl)
        if cached is not None:
            return cached, {"source": "cache", "api_calls": 0, "model": model}

        if not self.available:
            return None, {
                "source": "fallback", "api_calls": 0, "model": model,
                "reason": self.init_error or "ai_unavailable_or_circuit_open",
            }

        # Redis enforces the aggregate quota across Celery workers/replicas. The
        # local bucket remains a second guard when Redis is unavailable or delayed.
        for attempt in range(retries + 1):
            if not _global_rate_allow(AI_RPM) or not self.bucket.acquire():
                return None, {"source": "fallback", "api_calls": 0, "model": model, "reason": "rate_limited"}
            try:
                self.api_calls += 1
                _metric("ai_api_calls")
                kwargs = {}
                if json_mode or temperature is not None:
                    from google.genai import types
                    config_kwargs = {}
                    if json_mode:
                        config_kwargs["response_mime_type"] = "application/json"
                    if temperature is not None:
                        config_kwargs["temperature"] = float(temperature)
                    kwargs["config"] = types.GenerateContentConfig(**config_kwargs)
                response = self.client.models.generate_content(model=model, contents=prompt, **kwargs)
                text = getattr(response, "text", str(response))
                self._cache_put(key, text, cache_ttl)
                self.failures = 0
                return text, {"source": "gemini", "api_calls": 1, "model": model}
            except Exception as exc:
                self.failures += 1
                _metric("ai_failures")
                if self.failures >= 3:
                    self.open_until = time.time() + 60
                if attempt < retries:
                    time.sleep(2 ** attempt)
                else:
                    return None, {
                        "source": "fallback", "api_calls": 1, "model": model,
                        "reason": str(exc)[:200],
                    }


gateway = AIGateway()
