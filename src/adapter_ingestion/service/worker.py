# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import os
import time

from .factory import build_blob_store, build_control_plane, build_vault_repository
from .job_processor import process_one_job
from .observability import configure_logging, log_event
from .settings import load_settings


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Preconversion worker")
    parser.add_argument("--worker-id", default="", help="Worker identifier for job audit")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one job and exit",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="Sleep between polls when queue is empty",
    )
    return parser.parse_args()


def main() -> int:
    configure_logging()
    args = _parse_args()
    settings = load_settings()
    control_plane = build_control_plane(settings)
    blob_store = build_blob_store(settings)
    vault_repo = build_vault_repository(settings)
    worker_id = args.worker_id.strip() or os.getenv("HOSTNAME", "preconv-worker")
    log_event(
        "worker_started",
        workerId=worker_id,
        once=bool(args.once),
        pollSeconds=float(args.poll_seconds),
    )

    if args.once:
        processed = process_one_job(
            control_plane=control_plane,
            blob_store=blob_store,
            vault_repo=vault_repo,
            settings=settings,
            worker_id=worker_id,
        )
        log_event("worker_once_finished", workerId=worker_id, processedJobId=processed or "")
        return 0

    while True:
        processed_job_id = process_one_job(
            control_plane=control_plane,
            blob_store=blob_store,
            vault_repo=vault_repo,
            settings=settings,
            worker_id=worker_id,
        )
        if not processed_job_id:
            time.sleep(max(args.poll_seconds, 0.2))


if __name__ == "__main__":
    raise SystemExit(main())
