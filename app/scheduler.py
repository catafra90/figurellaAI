# app/scheduler.py
import os, sys, atexit, datetime, subprocess
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ========= CONFIG =========
# Default API job modules (rename to your actual modules when ready)
API_JOB_MODULES = [
    "app.common.api_agenda",
    "app.common.api_clients",
    "app.common.api_payments",
    # add more: "app.common.api_attendance", etc.
]

# Optional: override modules via env (comma-separated)
#   e.g. DATA_SYNC_MODULES=app.common.api_agenda,app.common.api_clients
_env_modules = os.environ.get("DATA_SYNC_MODULES", "").strip()
if _env_modules:
    API_JOB_MODULES = [m.strip() for m in _env_modules.split(",") if m.strip()]

# Optional common args passed to every module (space-separated)
#   e.g. DATA_SYNC_ARGS=--window_days 90 --center NEWTO
COMMON_ARGS = os.environ.get("DATA_SYNC_ARGS", "").split() if os.environ.get("DATA_SYNC_ARGS") else []

# Per-module timeout (seconds). Default 20 min.
MODULE_TIMEOUT_S = int(os.environ.get("DATA_SYNC_TIMEOUT_S", "1200"))


# ========= RUNTIME HELPERS =========
def _run_py_module(mod: str, args=None, timeout_s: int = MODULE_TIMEOUT_S) -> tuple[bool, str]:
    """
    Executes a Python module as: python -X utf8 -u -m <mod> [args...]
    Returns (ok, last_2000_chars_of_stdout_stderr).
    """
    cmd = [sys.executable, "-X", "utf8", "-u", "-m", mod]
    if args:
        cmd.extend(args)

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            env=env,
            cwd=os.getcwd(),
        )
        out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
        return (p.returncode == 0, out[-2000:])
    except subprocess.TimeoutExpired as e:
        return (False, f"[timeout {timeout_s}s] {e}")
    except Exception as e:
        return (False, f"[error] {e}")


_running_flag = False


# ========= PUBLIC API =========
def run_all_jobs(logger=None):
    """
    Runs each API data-sync job module once, sequentially.
    Each module should be invocable as a Python -m entrypoint.
    """
    global _running_flag
    if _running_flag:
        if logger:
            logger.warning("[scheduler] previous run still in progress — skipping.")
        return

    _running_flag = True
    try:
        now = datetime.datetime.now()
        if logger:
            logger.info("[scheduler] starting daily API jobs at %s", now)

        for mod in API_JOB_MODULES:
            if logger:
                logger.info("[scheduler] running %s ...", mod)
            ok, tail = _run_py_module(mod, args=COMMON_ARGS)
            if logger:
                (logger.info if ok else logger.warning)(
                    "[scheduler][%s] ok=%s tail:\n%s", mod, ok, tail
                )

        if logger:
            logger.info("[scheduler] finished daily API jobs.")
    finally:
        _running_flag = False


def start_scheduler(app=None):
    """
    Starts APScheduler to run `run_all_jobs` daily at a configured time,
    ONLY if ENABLE_INTERNAL_SCHEDULER=1.

    Env overrides:
      ENABLE_INTERNAL_SCHEDULER=1        -> enable
      SCHEDULE_HH=16                     -> hour (0-23), default 16 (4 PM)
      SCHEDULE_MM=0                      -> minute, default 0
      TZ=America/New_York                -> scheduler timezone (fallback to America/New_York)
    """
    if os.environ.get("ENABLE_INTERNAL_SCHEDULER") != "1":
        if app:
            app.logger.info("[scheduler] disabled (ENABLE_INTERNAL_SCHEDULER not set).")
        return None

    tz = os.environ.get("TZ", "America/New_York")
    hh = int(os.environ.get("SCHEDULE_HH", "16"))
    mm = int(os.environ.get("SCHEDULE_MM", "0"))

    sched = BackgroundScheduler(timezone=tz)
    sched.add_job(lambda: run_all_jobs(app.logger if app else None),
                  trigger=CronTrigger(hour=hh, minute=mm))

    sched.start()
    if app:
        app.logger.info("[scheduler] started (daily %02d:%02d %s)", hh, mm, tz)

    atexit.register(lambda: sched.shutdown(wait=False))
    return sched
