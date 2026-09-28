import argparse
import asyncio
import logging
from dataclasses import asdict
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from importer.specialization_importer import (
    read_specialization_urls,
    run_specialization_import,
    run_specialization_snapshot_import,
)
from importer.study_information import DEFAULT_STUDY_INFORMATION_DIRECTORY


DEFAULT_URLS_FILE = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "specializations_urls.txt"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import official DTU study specializations")
    parser.add_argument(
        "--url",
        help="Fetch and import one public DTU specialization URL instead of saved snapshots",
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        default=DEFAULT_URLS_FILE,
        help="URL list used to locate saved snapshots",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=DEFAULT_STUDY_INFORMATION_DIRECTORY,
        help="Root directory containing saved study information",
    )
    parser.add_argument("--limit", type=int, help="Limit the number of URLs for a test import")
    parser.add_argument("--request-delay", type=float, help="Seconds between DTU requests")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    urls = [args.url] if args.url else read_specialization_urls(str(args.urls_file))
    if args.limit is not None:
        urls = urls[: args.limit]
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    with SessionLocal() as session:
        if args.url:
            summary = asyncio.run(
                run_specialization_import(
                    session,
                    urls=urls,
                    request_delay=(
                        args.request_delay
                        if args.request_delay is not None
                        else settings.import_request_delay
                    ),
                )
            )
        else:
            summary = run_specialization_snapshot_import(
                session,
                urls=urls,
                snapshot_root=args.directory,
            )
    print("\nDTU specialization import complete")
    for key, value in asdict(summary).items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    if summary.failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
