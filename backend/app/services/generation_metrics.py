"""Cross-process Question Factory observability backed by Redis."""
from __future__ import annotations

import json
import time
from .cache import r

PREFIX = "metrics:question_factory"


def incr(name: str, amount: int = 1):
    try:
        r.incrby(f"{PREFIX}:{name}", amount)
    except Exception:
        pass


def record_rejection(reason: str):
    reason = (reason or "unknown")[:80]
    incr("rejected")
    try:
        r.hincrby(f"{PREFIX}:rejection_reasons", reason, 1)
    except Exception:
        pass


def record_latency(seconds: float):
    try:
        millis = max(0, int(seconds * 1000))
        r.incrby(f"{PREFIX}:latency_ms_sum", millis)
        r.incrby(f"{PREFIX}:latency_samples", 1)
    except Exception:
        pass


def snapshot() -> dict:
    names = [
        "requested", "accepted", "rejected", "duplicate", "verification_failed",
        "difficulty_mismatch", "difficulty_reassigned", "diversity_rejected", "distractor_failed",
        "proposal_invalid", "ai_unavailable", "retry_scheduled", "queue_deduped",
        "latency_ms_sum", "latency_samples",
    ]
    try:
        values = {name: int(r.get(f"{PREFIX}:{name}") or 0) for name in names}
        samples = values.pop("latency_samples", 0)
        total_ms = values.pop("latency_ms_sum", 0)
        values["avg_generation_latency_ms"] = round(total_ms / samples, 1) if samples else 0.0
        values["acceptance_rate"] = round(values["accepted"] / max(1, values["accepted"] + values["rejected"]), 4)
        values["rejection_reasons"] = {k: int(v) for k, v in r.hgetall(f"{PREFIX}:rejection_reasons").items()}
        return values
    except Exception:
        return {name: 0 for name in names if not name.startswith("latency_")} | {
            "avg_generation_latency_ms": 0.0, "acceptance_rate": 0.0, "rejection_reasons": {}
        }
