# app/scheduler.py
import os, sys, atexit, datetime, subprocess
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

SCRAPER_MODULES = [
    "app.common.scrape_agenda",
    "app.common.scrape_contracts",
    "app.common.scrape_customer_acquisitions",
    "app.common.scrape_ibf",
    "app.common.scrape_last_session",
    "app.common.scrape_payments_done",
    "app.common.scrape_payments_due",
    "app.common.scrape_pip",
    "app.common.scrape_subscriptions",
]

COMMON_ARGS = []  # e.g. ["01/01/2025","08/31/2025"] if you want a fixed window

def _run_py_module(mod: str, args=None, timeout_s: int = 1200) -> tuple[bool, str]:
    cmd = [sys.executable, "-X", "utf8", "-u", "-m", mod]
    if args: cmd.extend(args)
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout_s, env=env, cwd=os.getcwd()
        )
        out = (p.stdout or "") + ("\n" + p.stderr if p.stderr else "")
        return (p.returncode == 0, out[-2000:])
    except subprocess.TimeoutExpired as e:
        return (False, f"[timeout {timeout_s}s] {e}")
    except Exception as e:
        return (False, f"[error] {e}")

_running_flag = False

def run_all_scrapers(logger=None):
    """Run each scraper once, sequentially."""
    global _running_flag
    if _running_flag:
        if logger: logger.warning("[scheduler] previous run still in progress — skipping.")
        return
    _running_flag = True
    try:
        if logger: logger.info("[scheduler] starting daily scraper run at %s", datetime.datetime.now())
        for mod in SCRAPER_MODULES:
            if logger: logger.info("[scheduler] running %s ...", mod)
            ok, tail = _run_py_module(mod, args=COMMON_ARGS)
            if logger:
                (logger.info if ok else logger.warning)(
                    "[scheduler][%s] ok=%s tail:\n%s", mod, ok, tail
                )
        if logger: logger.info("[scheduler] finished daily scraper run.")
    finally:
        _running_flag = False

def start_scheduler(app=None):
    """Schedule run_all_scrapers daily at 16:00 America/New_York if ENABLE_INTERNAL_SCHEDULER=1."""
    if os.environ.get("ENABLE_INTERNAL_SCHEDULER") != "1":
        if app: app.logger.info("[scheduler] disabled (ENABLE_INTERNAL_SCHEDULER not set).")
        return None
    sched = BackgroundScheduler(timezone="America/New_York")
    sched.add_job(lambda: run_all_scrapers(app.logger if app else None),
                  trigger=CronTrigger(hour=16, minute=0))
    sched.start()
    if app: app.logger.info("[scheduler] started (daily 4:00 PM America/New_York)")
    atexit.register(lambda: sched.shutdown(wait=False))
    return sched
