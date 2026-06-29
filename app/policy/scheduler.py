"""
Policy Scheduler — Phase 7.

Wires scraper → differ → service into a scheduled job.

Two modes:
  1. Embedded in FastAPI (call start_scheduler(app) from main.py lifespan).
  2. Standalone cron:  python -m app.policy.scheduler
     (useful for serverless / external cron like Railway CRON jobs)

APScheduler is only imported if POLICY_SCHEDULER_ENABLED=true to avoid
adding a hard startup dependency when you don't need it.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import SessionLocal
from app.policy.scraper import scrape_sources, DEFAULT_SOURCES
from app.policy.differ import diff_all
from app.policy.service import build_live_snapshot_map, persist_drafts

logger = logging.getLogger(__name__)

SCHEDULER_ENABLED = settings.policy_scheduler_enabled
# How often to run. Default: once per day at 03:00.
SCHEDULE_HOUR = settings.policy_schedule_hour
SCHEDULE_MINUTE = settings.policy_schedule_minute


# ---------------------------------------------------------------------------
# Core job function (no scheduler dependency — unit-testable)
# ---------------------------------------------------------------------------

def run_policy_check(db: Session | None = None) -> dict:
    """
    Execute one full policy-check cycle:
      1. Load current live rules from DB (snapshot).
      2. Scrape all configured sources.
      3. Diff scraped vs live.
      4. Persist diffs as PolicyDraft rows.

    Returns a summary dict suitable for logging or health endpoint.
    Never raises — errors per-source are logged and skipped.
    """
    started_at = datetime.now(timezone.utc)
    own_db = db is None

    if own_db:
        db = SessionLocal()

    try:
        live_map = build_live_snapshot_map(db)
        scraped = scrape_sources(DEFAULT_SOURCES)
        diffs = diff_all(scraped, live_map)
        drafts = persist_drafts(db, diffs)

        summary = {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "sources_attempted": len(DEFAULT_SOURCES),
            "sources_parsed": len(scraped),
            "diffs_detected": len(diffs),
            "drafts_created": len(drafts),
        }
        logger.info(f"Policy check complete: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Policy check failed: {e}", exc_info=True)
        return {
            "started_at": started_at.isoformat(),
            "error": str(e),
        }
    finally:
        if own_db:
            db.close()


# ---------------------------------------------------------------------------
# APScheduler integration (optional)
# ---------------------------------------------------------------------------

def start_scheduler(app=None) -> None:
    """
    Start the APScheduler background scheduler.
    Call from FastAPI lifespan or app startup if POLICY_SCHEDULER_ENABLED=true.

    app: FastAPI instance (unused currently, kept for future state passing).
    """
    if not SCHEDULER_ENABLED:
        logger.info("Policy scheduler disabled (POLICY_SCHEDULER_ENABLED != true)")
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError:
        logger.error(
            "apscheduler not installed — policy scheduler will not run. "
            "Add apscheduler to requirements.txt."
        )
        return

    scheduler = BackgroundScheduler(timezone="Asia/Karachi")
    scheduler.add_job(
        run_policy_check,
        trigger=CronTrigger(hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE),
        id="policy_check",
        name="LGU Policy Update Check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Policy scheduler started — runs daily at "
        f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} PKT"
    )


# ---------------------------------------------------------------------------
# Standalone entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.info("Running policy check (standalone mode)…")
    summary = run_policy_check()
    print(summary)
    sys.exit(0 if "error" not in summary else 1)
