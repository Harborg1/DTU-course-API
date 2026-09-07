import argparse
import logging
from dataclasses import asdict
from pathlib import Path

from app.database import SessionLocal
from importer.course_xml_importer import import_course_xml_directory


DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "app" / "data" / "course_information"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import saved DTU GetCourse XML into PostgreSQL")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--academic-year", default="2026-2027")
    parser.add_argument("--limit", type=int)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        with SessionLocal() as session:
            summary = import_course_xml_directory(
                session,
                args.directory,
                academic_year=args.academic_year,
                limit=args.limit,
            )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not import course XML: {exc}") from exc

    print("Course XML import complete")
    for key, value in asdict(summary).items():
        print(f"{key.replace('_', ' ').title()}: {value}")
    if summary.courses_failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
