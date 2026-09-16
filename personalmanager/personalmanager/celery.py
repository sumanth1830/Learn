import os
from celery import Celery
import billiard
from celery.schedules import crontab

billiard.context._force_start_method('spawn')
os.environ['FORKED_BY_MULTIPROCESSING'] = '1'

for var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
            "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(var, "1")
os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "personalmanager.settings")
app = Celery("personalmanager")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.worker_max_tasks_per_child = 20
app.conf.beat_schedule = {
    "cleanup-stuck-quizzes": {
        "task": "quizmaker.tasks.cleanup_stuck_quizzes",
        "schedule": crontab(minute="*/30"),
    },
    # PIB Ingestion
    "poll-pib-feed": {
        "task": "quizmaker.tasks.poll_pib_feed_task",
        "schedule": crontab(minute=0, hour="*/6"),
    },
}