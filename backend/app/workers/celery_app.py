import ssl
from celery import Celery
from ..core.config import settings

celery = Celery("quantforge", broker=settings.redis_url, backend=settings.redis_url)

conf = {
    "task_acks_late": True,
    "task_reject_on_worker_lost": True,
    "worker_prefetch_multiplier": 1,
    "task_track_started": False,
    "broker_connection_retry_on_startup": True,
    "result_expires": 1800,
    "worker_max_tasks_per_child": 250,
    "broker_connection_timeout": 5,
    "task_publish_retry": False,
    "broker_transport_options": {"visibility_timeout": 300, "socket_connect_timeout": 5, "socket_timeout": 5},
    "beat_schedule": {
        "dispatch-durable-generation": {
            "task": "app.workers.tasks.dispatch_generation_jobs", "schedule": 10.0,
        },
    },
    "task_routes": {"app.workers.tasks.*": {"queue": "generation"}},
}
if settings.redis_url.startswith("rediss://"):
    conf["broker_use_ssl"] = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    conf["redis_backend_use_ssl"] = {"ssl_cert_reqs": ssl.CERT_REQUIRED}

celery.conf.update(**conf)
celery.conf.imports = ("app.workers.tasks",)
