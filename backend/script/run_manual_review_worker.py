"""Reliable manual-review outbox and claim-reaper worker."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from service.manual_review_production import manual_review_service

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("manual-review-worker")


async def main():
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    poll = max(float(os.getenv("REVIEW_OUTBOX_POLL_SECONDS", "2")), 0.2)
    while not stop.is_set():
        try:
            result = await manual_review_service.process_outbox(
                int(os.getenv("REVIEW_OUTBOX_BATCH_SIZE", "20"))
            )
            reclaimed = manual_review_service.reclaim_expired(
                int(os.getenv("REVIEW_HEARTBEAT_TIMEOUT_MINUTES", "5"))
            )
            if result["processed"] or result["failed"] or reclaimed:
                log.info("outbox=%s reclaimed=%s", result, reclaimed)
        except Exception:
            log.exception("manual review worker iteration failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except TimeoutError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
