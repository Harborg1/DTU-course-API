import argparse
import asyncio
import logging
from dataclasses import asdict

from app.config import get_settings
from app.database import SessionLocal
from importer.specialization_importer import read_specialization_urls, run_specialization_import


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import official DTU study specializations")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="Import one public DTU specialization URL")
    source.add_argument("--urls-file", help="Import HTTPS URLs listed in a text file")
    parser.add_argument("--limit", type=int, help="Limit the number of URLs for a test import")
    parser.add_argument("--request-delay", type=float, help="Seconds between DTU requests")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    urls = [args.url] if args.url else read_specialization_urls(args.urls_file)
    if args.limit is not None:
        urls = urls[: args.limit]
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    with SessionLocal() as session:
        summary = asyncio.run(
            run_specialization_import(
                session,
                urls=urls,
                request_delay=(
                    args.request_delay if args.request_delay is not None else settings.import_request_delay
                ),
            )
        )
    print("\nDTU specialization import complete")
    for key, value in asdict(summary).items():
        print(f"{key.replace('_', ' ').title()}: {value}")


if __name__ == "__main__":
    main()
