from __future__ import annotations

import argparse
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from xml.etree import ElementTree


COURSE_NUMBER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,15}$")
DEFAULT_CURRENT_NUMBERS = Path("course_numbers.txt")
DEFAULT_CURRENT_COURSE_DIRECTORY = Path("app/data/course_information")
REPORT_ITEM_LIMIT = 100


@dataclass(frozen=True)
class SnapshotDifference:
    added_courses: tuple[str, ...]
    removed_courses: tuple[str, ...]
    changed_courses: tuple[str, ...]
    missing_current_xml: tuple[str, ...]
    unlisted_current_xml: tuple[str, ...]
    number_order_changed: bool

    @property
    def has_changes(self) -> bool:
        return any(
            (
                self.added_courses,
                self.removed_courses,
                self.changed_courses,
                self.missing_current_xml,
                self.unlisted_current_xml,
            )
        ) or self.number_order_changed


def read_course_numbers(path: Path) -> tuple[str, ...]:
    numbers: list[str] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        number = line.strip().upper()
        if not number:
            continue
        if not COURSE_NUMBER_PATTERN.fullmatch(number):
            raise ValueError(f"invalid course number on line {line_number} in {path}: {number!r}")
        if number in seen:
            raise ValueError(f"duplicate course number in {path}: {number}")
        seen.add(number)
        numbers.append(number)
    if not numbers:
        raise ValueError(f"no course numbers found in {path}")
    return tuple(numbers)


def xml_files(directory: Path) -> dict[str, Path]:
    if not directory.is_dir():
        raise ValueError(f"course XML directory does not exist: {directory}")
    return {path.stem.upper(): path for path in sorted(directory.glob("*.txt"))}


def canonical_xml(path: Path) -> str:
    try:
        return ElementTree.canonicalize(from_file=path, strip_text=True)
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"could not parse XML in {path}: {exc}") from exc


def compare_snapshots(
    *,
    fresh_numbers_path: Path,
    fresh_course_directory: Path,
    current_numbers_path: Path,
    current_course_directory: Path,
) -> SnapshotDifference:
    fresh_order = read_course_numbers(fresh_numbers_path)
    current_order = read_course_numbers(current_numbers_path)
    fresh_numbers = set(fresh_order)
    current_numbers = set(current_order)
    fresh_files = xml_files(fresh_course_directory)
    current_files = xml_files(current_course_directory)

    if fresh_numbers != set(fresh_files):
        missing = sorted(fresh_numbers - set(fresh_files))
        unlisted = sorted(set(fresh_files) - fresh_numbers)
        raise ValueError(
            "fresh download is internally inconsistent: "
            f"missing XML={missing}, unlisted XML={unlisted}"
        )

    # Parse every fresh file, including newly published courses, before applying it.
    fresh_canonical = {number: canonical_xml(path) for number, path in fresh_files.items()}
    shared_files = fresh_numbers & current_numbers & set(current_files)
    changed = tuple(
        sorted(
            number
            for number in shared_files
            if fresh_canonical[number] != canonical_xml(current_files[number])
        )
    )

    return SnapshotDifference(
        added_courses=tuple(sorted(fresh_numbers - current_numbers)),
        removed_courses=tuple(sorted(current_numbers - fresh_numbers)),
        changed_courses=changed,
        missing_current_xml=tuple(sorted(current_numbers - set(current_files))),
        unlisted_current_xml=tuple(sorted(set(current_files) - current_numbers)),
        number_order_changed=fresh_order != current_order and fresh_numbers == current_numbers,
    )


def apply_fresh_snapshot(
    *,
    fresh_numbers_path: Path,
    fresh_course_directory: Path,
    current_numbers_path: Path,
    current_course_directory: Path,
) -> None:
    fresh_files = xml_files(fresh_course_directory)
    current_course_directory.mkdir(parents=True, exist_ok=True)
    current_numbers_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fresh_numbers_path, current_numbers_path)

    for current_path in current_course_directory.glob("*.txt"):
        if current_path.stem.upper() not in fresh_files:
            current_path.unlink()
    for number, fresh_path in fresh_files.items():
        shutil.copyfile(fresh_path, current_course_directory / f"{number}.txt")


def _report_items(title: str, items: tuple[str, ...]) -> list[str]:
    lines = [f"## {title} ({len(items)})", ""]
    if not items:
        return [*lines, "None.", ""]
    lines.extend(f"- `{item}`" for item in items[:REPORT_ITEM_LIMIT])
    if len(items) > REPORT_ITEM_LIMIT:
        lines.append(f"- … and {len(items) - REPORT_ITEM_LIMIT} more")
    lines.append("")
    return lines


def render_report(
    difference: SnapshotDifference,
    *,
    catalog_version: str,
    fresh_course_count: int,
) -> str:
    status = "Changes detected" if difference.has_changes else "No changes detected"
    lines = [
        "# DTU course data refresh",
        "",
        f"- Status: **{status}**",
        f"- Catalog version: `{catalog_version}`",
        f"- Courses in fresh snapshot: **{fresh_course_count}**",
        f"- Checked at: `{datetime.now(UTC).isoformat()}`",
        "",
    ]
    lines.extend(_report_items("New courses", difference.added_courses))
    lines.extend(_report_items("Removed courses", difference.removed_courses))
    lines.extend(_report_items("Changed course XML", difference.changed_courses))
    lines.extend(_report_items("Missing XML in repository", difference.missing_current_xml))
    lines.extend(_report_items("Unlisted XML in repository", difference.unlisted_current_xml))
    if difference.number_order_changed:
        lines.extend(
            [
                "## Course-number ordering",
                "",
                "The course-number set is unchanged, but its ordering differs.",
                "",
            ]
        )
    lines.extend(
        [
            "Supabase was not accessed or modified by this refresh.",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare a fresh DTU course snapshot with the repository snapshot"
    )
    parser.add_argument("--fresh-numbers", type=Path, required=True)
    parser.add_argument("--fresh-course-directory", type=Path, required=True)
    parser.add_argument("--current-numbers", type=Path, default=DEFAULT_CURRENT_NUMBERS)
    parser.add_argument(
        "--current-course-directory",
        type=Path,
        default=DEFAULT_CURRENT_COURSE_DIRECTORY,
    )
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    difference = compare_snapshots(
        fresh_numbers_path=args.fresh_numbers,
        fresh_course_directory=args.fresh_course_directory,
        current_numbers_path=args.current_numbers,
        current_course_directory=args.current_course_directory,
    )
    report = render_report(
        difference,
        catalog_version=args.catalog_version,
        fresh_course_count=len(read_course_numbers(args.fresh_numbers)),
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report)
    print(report)

    if difference.has_changes and args.apply:
        apply_fresh_snapshot(
            fresh_numbers_path=args.fresh_numbers,
            fresh_course_directory=args.fresh_course_directory,
            current_numbers_path=args.current_numbers,
            current_course_directory=args.current_course_directory,
        )


if __name__ == "__main__":
    main()
