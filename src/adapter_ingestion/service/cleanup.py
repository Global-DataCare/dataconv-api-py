# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json

from .factory import build_control_plane
from .observability import configure_logging, log_event
from .settings import load_settings


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Delete expired terminal conversion jobs across all tenants.",
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=None,
        help=(
            "Override PRECONV_JOB_RESULT_TTL_SECONDS. "
            "Use -1 to disable expiration checks."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report what would be deleted without removing jobs.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Maximum number of jobs to delete in this run (0 = no limit).",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print JSON report with indentation.",
    )
    return parser


def main() -> int:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    settings = load_settings()
    ttl_seconds = settings.job_result_ttl_seconds if args.ttl_seconds is None else int(args.ttl_seconds)
    control_plane = build_control_plane(settings)

    report = control_plane.cleanup_expired_jobs(
        ttl_seconds=ttl_seconds,
        dry_run=bool(args.dry_run),
        limit=int(args.limit or 0),
        include_details=True,
    )
    details = report.get("details", [])
    if isinstance(details, list):
        for item in details:
            if not isinstance(item, dict):
                continue
            log_event(
                "job_cleanup_expired_evaluated",
                source="cleanup-cron",
                dryRun=bool(args.dry_run),
                deleted=bool(item.get("deleted", False)),
                delivered=bool(item.get("delivered", False)),
                **item,
            )
        if details:
            expired_undelivered = sum(
                1
                for item in details
                if isinstance(item, dict)
                and bool(item.get("deleted", False))
                and not bool(item.get("delivered", False))
            )
            log_event(
                "job_cleanup_summary",
                source="cleanup-cron",
                dryRun=bool(args.dry_run),
                ttlSeconds=ttl_seconds,
                scanned=report.get("scanned", 0),
                terminal=report.get("terminal", 0),
                expired=report.get("expired", 0),
                deleted=report.get("deleted", 0),
                expiredUndeliveredDeleted=expired_undelivered,
            )
    payload = {
        "ttlSeconds": ttl_seconds,
        "dryRun": bool(args.dry_run),
        "limit": int(args.limit or 0),
        "scanned": int(report.get("scanned", 0) or 0),
        "terminal": int(report.get("terminal", 0) or 0),
        "expired": int(report.get("expired", 0) or 0),
        "deleted": int(report.get("deleted", 0) or 0),
    }
    if args.pretty:
        print(json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
