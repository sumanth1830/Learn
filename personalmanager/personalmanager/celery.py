import os
from celery import Celery
import billiard

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