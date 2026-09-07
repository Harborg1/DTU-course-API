import argparse
import logging
from dataclasses import asdict
from pathlib import Path

from app.database import SessionLocal
from importer.course_xml_importer import import_course_xml_directory


DEFAULT_DIRECTORY = Path(__file__).resolve().parents[1] / "app" / "data" / "course_information"


def read_course_number_snapshot(path: Path) -> set[str]:
    numbers = {line.strip().upper() for line in path.read_text().splitlines() if line.strip()}
    if not numbers:
        raise ValueError(f"no course numbers found in {path}")
    return numbers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import saved DTU GetCourse XML into PostgreSQL")
    parser.add_argument("--directory", type=Path, default=DEFAULT_DIRECTORY)
    parser.add_argument("--academic-year", default="2026-2027")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--prune",
        action="store_true",
        help="Delete database courses for the academic year that are absent from the snapshot",
    )
    parser.add_argument(
        "--course-numbers",
        type=Path,
        help="Complete course-number snapshot required when --prune is used",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if args.prune and args.limit is not None:
        raise SystemExit("--prune cannot be combined with --limit")
    if args.prune and args.course_numbers is None:
        raise SystemExit("--prune requires --course-numbers")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        snapshot_course_numbers = (
            read_course_number_snapshot(args.course_numbers) if args.course_numbers else None
        )
        with SessionLocal() as session:
            summary = import_course_xml_directory(
                session,
                args.directory,
                academic_year=args.academic_year,
                limit=args.limit,
                prune=args.prune,
                snapshot_course_numbers=snapshot_course_numbers,
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
