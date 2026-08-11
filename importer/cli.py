import argparse
import asyncio
import logging
from dataclasses import asdict

from app.config import get_settings
from app.database import SessionLocal
from importer.importer import run_import


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import official DTU courses")
    parser.add_argument("--academic-year", default=None, help="Academic year, e.g. 2026-2027")
    parser.add_argument("--course", help="Import one course number")
    parser.add_argument("--retry-failed", action="store_true", help="Retry stored failures only")
    parser.add_argument("--limit", type=int, help="Limit the number of courses for a test import")
    parser.add_argument("--request-delay", type=float, help="Seconds between DTU requests")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    academic_year = args.academic_year or settings.default_academic_year
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if args.course and args.retry_failed:
        raise SystemExit("--course and --retry-failed cannot be combined")
    with SessionLocal() as session:
        summary = asyncio.run(
            run_import(
                session,
                academic_year=academic_year,
                base_url=settings.dtu_base_url,
                request_delay=args.request_delay if args.request_delay is not None else settings.import_request_delay,
                course=args.course,
                retry_failed=args.retry_failed,
                limit=args.limit,
            )
        )
    print("\nDTU import complete")
    for key, value in asdict(summary).items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()

