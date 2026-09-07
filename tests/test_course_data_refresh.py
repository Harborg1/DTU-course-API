from pathlib import Path

import pytest

from github_actions.course_data_refresh import (
    apply_fresh_snapshot,
    canonical_xml,
    compare_snapshots,
    render_report,
)


def _write_xml(directory: Path, course_number: str, title: str, *, compact: bool = True) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if compact:
        content = f'<root><Course CourseCode="{course_number}" Title="{title}" /></root>'
    else:
        content = (
            "<root>\n"
            f'  <Course Title="{title}" CourseCode="{course_number}"/>\n'
            "</root>\n"
        )
    (directory / f"{course_number}.txt").write_text(content)


def test_canonical_xml_ignores_formatting_and_attribute_order(tmp_path):
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text('<root><Course CourseCode="01001" Title="Math" /></root>')
    second.write_text('<root>\n <Course Title="Math" CourseCode="01001"/>\n</root>')

    assert canonical_xml(first) == canonical_xml(second)


def test_compares_and_applies_fresh_snapshot(tmp_path):
    current_numbers = tmp_path / "current_numbers.txt"
    fresh_numbers = tmp_path / "fresh_numbers.txt"
    current_directory = tmp_path / "current"
    fresh_directory = tmp_path / "fresh"
    current_numbers.write_text("01001\n01002\n")
    fresh_numbers.write_text("01001\n01003\n")
    _write_xml(current_directory, "01001", "Old title")
    _write_xml(current_directory, "01002", "Removed course")
    _write_xml(current_directory, "09999", "Unlisted course")
    _write_xml(fresh_directory, "01001", "New title")
    _write_xml(fresh_directory, "01003", "New course")

    difference = compare_snapshots(
        fresh_numbers_path=fresh_numbers,
        fresh_course_directory=fresh_directory,
        current_numbers_path=current_numbers,
        current_course_directory=current_directory,
    )

    assert difference.added_courses == ("01003",)
    assert difference.removed_courses == ("01002",)
    assert difference.changed_courses == ("01001",)
    assert difference.unlisted_current_xml == ("09999",)
    assert difference.has_changes
    assert "Supabase was not accessed" in render_report(
        difference,
        catalog_version="2026/2027",
        fresh_course_count=2,
    )

    apply_fresh_snapshot(
        fresh_numbers_path=fresh_numbers,
        fresh_course_directory=fresh_directory,
        current_numbers_path=current_numbers,
        current_course_directory=current_directory,
    )

    assert current_numbers.read_text() == fresh_numbers.read_text()
    assert sorted(path.name for path in current_directory.glob("*.txt")) == [
        "01001.txt",
        "01003.txt",
    ]
    assert canonical_xml(current_directory / "01001.txt") == canonical_xml(
        fresh_directory / "01001.txt"
    )


def test_rejects_incomplete_fresh_snapshot(tmp_path):
    current_numbers = tmp_path / "current_numbers.txt"
    fresh_numbers = tmp_path / "fresh_numbers.txt"
    current_directory = tmp_path / "current"
    fresh_directory = tmp_path / "fresh"
    current_numbers.write_text("01001\n")
    fresh_numbers.write_text("01001\n01002\n")
    _write_xml(current_directory, "01001", "Current")
    _write_xml(fresh_directory, "01001", "Fresh")

    with pytest.raises(ValueError, match="fresh download is internally inconsistent"):
        compare_snapshots(
            fresh_numbers_path=fresh_numbers,
            fresh_course_directory=fresh_directory,
            current_numbers_path=current_numbers,
            current_course_directory=current_directory,
        )
