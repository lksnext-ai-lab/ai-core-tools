"""Asyncio worker loop for the crawl pipeline. Started in FastAPI lifespan."""
import asyncio
import os
import uuid
from typing import List

from utils.logger import get_logger

logger = get_logger(__name__)

CRAWL_POLL_INTERVAL_SECONDS = int(os.getenv('CRAWL_POLL_INTERVAL_SECONDS', '5'))
CRAWL_WORKER_CONCURRENCY = int(os.getenv('CRAWL_WORKER_CONCURRENCY', '2'))
CRAWL_SCHEDULER_INTERVAL_SECONDS = 60


async def _worker_loop(worker_id: str) -> None:
    """Single worker coroutine — polls for QUEUED jobs and runs them."""
    from db.database import SessionLocal
    from services.crawl_executor_service import CrawlExecutorService
    from repositories.crawl_job_repository import CrawlJobRepository

    while True:
        try:
            db = SessionLocal()
            try:
                job = CrawlJobRepository.poll_queued_job(worker_id, db)
            finally:
                db.close()

            if job:
                logger.info(f"Worker {worker_id} picked up job {job.id}")
                await CrawlExecutorService.run_job(job.id)
            else:
                await asyncio.sleep(CRAWL_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} shutting down")
            break
        except Exception as e:
            logger.error(f"Worker {worker_id} error: {e}", exc_info=True)
            await asyncio.sleep(CRAWL_POLL_INTERVAL_SECONDS)


async def _scheduler_loop() -> None:
    """Periodic scheduler coroutine."""
    from db.database import SessionLocal
    from services.crawl_scheduler_service import CrawlSchedulerService

    while True:
        try:
            db = SessionLocal()
            try:
                count = await CrawlSchedulerService.run_once(db)
                if count:
                    logger.info(f"Scheduler enqueued {count} job(s)")
            finally:
                db.close()
            await asyncio.sleep(CRAWL_SCHEDULER_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("Scheduler loop shutting down")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            await asyncio.sleep(CRAWL_SCHEDULER_INTERVAL_SECONDS)


async def start_crawl_workers(app) -> List[asyncio.Task]:
    """
    Start all crawl worker tasks. Called during FastAPI lifespan startup.
    Performs heartbeat recovery for stuck jobs before starting workers.
    """
    from db.database import SessionLocal
    from repositories.crawl_job_repository import CrawlJobRepository

    # Recover stuck jobs from previous process shutdown
    db = SessionLocal()
    try:
        recovered = CrawlJobRepository.reset_stuck_jobs(db)
        if recovered:
            logger.info(f"Startup: recovered {recovered} stuck crawl job(s)")
    finally:
        db.close()

    tasks: List[asyncio.Task] = [
        asyncio.create_task(
            _worker_loop(str(uuid.uuid4())),
            name=f"crawl-worker-{i}",
        )
        for i in range(CRAWL_WORKER_CONCURRENCY)
    ]
    tasks.append(asyncio.create_task(_scheduler_loop(), name="crawl-scheduler"))
    return tasks


async def stop_crawl_workers(tasks: List[asyncio.Task]) -> None:
    """Cancel all crawl worker tasks. Called during FastAPI lifespan shutdown."""
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
