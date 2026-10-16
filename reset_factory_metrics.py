from backend.app.services.cache import r

PREFIX = "metrics:question_factory"

keys = [
    "requested",
    "accepted",
    "rejected",
    "duplicate",
    "verification_failed",
    "difficulty_mismatch",
    "difficulty_reassigned",
    "diversity_rejected",
    "distractor_failed",
    "proposal_invalid",
    "ai_unavailable",
    "retry_scheduled",
    "queue_deduped",
    "latency_ms_sum",
    "latency_samples",
    "rejection_reasons",
    "recent_rejections",
]

redis_keys = [f"{PREFIX}:{name}" for name in keys]

deleted = r.delete(*redis_keys)

print(f"Deleted {deleted} Question Factory metric keys.")