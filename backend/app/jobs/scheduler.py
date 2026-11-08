from apscheduler.schedulers.blocking import BlockingScheduler
from app.jobs.daily_sync_job import run_daily_sync

scheduler = BlockingScheduler()

scheduler.add_job(
    run_daily_sync,
    "cron",
    hour=23,
    minute=59
)

if __name__ == "__main__":
    scheduler.start()