from redis import Redis
from ..core.config import settings

r = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=3, socket_timeout=3)


def _incr(name: str, amount: int = 1):
    try:
        r.incrby(f"metrics:{name}", amount)
    except Exception:
        pass


def record_quiz_started():
    _incr("quiz_started")


def record_replenish_requested():
    _incr("replenish_requested")


def record_pool_shortage():
    _incr("pool_shortage")


def record_variant_collision():
    _incr("variant_collision")


def redis_stats():
    try:
        r.ping()
        return {
            "connected": True,
            "quiz_sessions_started": int(r.get("metrics:quiz_started") or 0),
            "replenish_requests": int(r.get("metrics:replenish_requested") or 0),
            "pool_shortages": int(r.get("metrics:pool_shortage") or 0),
            "variant_collisions": int(r.get("metrics:variant_collision") or 0),
            "ai_api_calls": int(r.get("metrics:ai_api_calls") or 0),
            "ai_cache_hits": int(r.get("metrics:ai_cache_hit") or 0),
            "ai_failures": int(r.get("metrics:ai_failures") or 0),
            "role": "Celery broker, distributed rate limiting, shared AI cache, and cross-process metrics",
        }
    except Exception:
        return {
            "connected": False,
            "quiz_sessions_started": 0,
            "replenish_requests": 0,
            "pool_shortages": 0,
            "variant_collisions": 0,
            "ai_api_calls": 0,
            "ai_cache_hits": 0,
            "ai_failures": 0,
            "role": "Celery broker, distributed rate limiting, shared AI cache, and cross-process metrics",
        }


def rate_limit(key: str, limit: int, window_seconds: int = 60) -> bool:
    """Redis fixed-window limiter. Production can fail closed if Redis is unavailable."""
    try:
        k = f"ratelimit:{key}"
        # INCR + first-window expiry are atomic so a network interruption cannot
        # leave a permanent counter without TTL.
        value = int(r.eval(
            "local n=redis.call('INCR',KEYS[1]); "
            "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",
            1, k, window_seconds,
        ))
        return value <= limit
    except Exception:
        return bool(settings.rate_limit_fail_open)


def redis_ready() -> bool:
    try:
        return bool(r.ping())
    except Exception:
        return False


def reserve_generation_jobs(domain: str, difficulty: str, requested: int, max_pending: int, ttl_seconds: int = 1800) -> int:
    """Atomically reserve queue capacity for a topic/difficulty bucket.

    This prevents Celery Beat and manual replenishment from repeatedly stacking
    the same deficit while earlier jobs are still queued/running.
    """
    requested = max(0, int(requested))
    max_pending = max(1, int(max_pending))
    try:
        key = f"generation:pending:{domain}:{difficulty}"
        allowed = int(r.eval(
            "local current=tonumber(redis.call('GET',KEYS[1]) or '0'); "
            "local requested=tonumber(ARGV[1]); local cap=tonumber(ARGV[2]); "
            "local room=cap-current; if room<0 then room=0 end; "
            "local take=requested; if take>room then take=room end; "
            "if take>0 then redis.call('INCRBY',KEYS[1],take); redis.call('EXPIRE',KEYS[1],ARGV[3]); end; "
            "return take",
            1, key, requested, max_pending, ttl_seconds,
        ))
        return allowed
    except Exception:
        # In development, queueing can still work without Redis bookkeeping.
        return min(requested, max_pending) if settings.rate_limit_fail_open else 0


def release_generation_job(domain: str, difficulty: str) -> None:
    try:
        key = f"generation:pending:{domain}:{difficulty}"
        r.eval(
            "local current=tonumber(redis.call('GET',KEYS[1]) or '0'); "
            "if current<=1 then redis.call('DEL',KEYS[1]); return 0 end; "
            "return redis.call('DECR',KEYS[1])",
            1, key,
        )
    except Exception:
        pass


def pending_generation_jobs(domain: str, difficulty: str) -> int:
    try:
        return int(r.get(f"generation:pending:{domain}:{difficulty}") or 0)
    except Exception:
        return 0
