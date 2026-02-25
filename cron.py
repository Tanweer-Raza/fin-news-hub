from apscheduler.schedulers.blocking import BlockingScheduler
import logging
import sys
import os
from pathlib import Path
from crawler import run


Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    filename="logs/scheduler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def job():
    try:
        logging.info("Scheduled crawl started")
        run()
        logging.info("Scheduled crawl finished")
    except Exception as e:
        logging.critical(f"Scheduler crashed: {e}")


scheduler = BlockingScheduler()

# daily 6 AM
scheduler.add_job(job, "cron", hour=19, minute=53)

logging.info("Scheduler running - at 19:53")
scheduler.start()
