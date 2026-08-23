import asyncio
from pathlib import Path

import httpx
import pytest

from scripts.get_all_course_information import (
    CourseResponseError,
    download_course_information,
    normalize_year_group,
    read_course_numbers,
    validate_course_xml,
)


FIXTURES = Path(__file__).parent / "fixtures"
COURSE_XML = (FIXTURES / "course_02452.xml").read_bytes()


@pytest.mark.parametrize("value", ["2026/2027", "2026-2027"])
def test_normalizes_year_group(value):
    assert normalize_year_group(value) == "2026/2027"


def test_reads_validated_sorted_unique_course_numbers(tmp_path):
    input_path = tmp_path / "numbers.txt"
    input_path.write_text("02452\n01001\n02452\n\n")
    assert read_course_numbers(input_path) == ["01001", "02452"]


def test_rejects_invalid_course_number(tmp_path):
    input_path = tmp_path / "numbers.txt"
    input_path.write_text("02452\nnot/a/course\n")
    with pytest.raises(ValueError, match="line 2"):
        read_course_numbers(input_path)


def test_validates_course_number_and_year_in_xml():
    validate_course_xml(COURSE_XML, "02452", "2026/2027")
    with pytest.raises(CourseResponseError, match="did not contain"):
        validate_course_xml(COURSE_XML, "01001", "2026/2027")
    with pytest.raises(CourseResponseError, match="expected"):
        validate_course_xml(COURSE_XML, "02452", "2025/2026")


def test_downloads_each_course_to_a_separate_txt_file(tmp_path):
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        course_number = request.url.params["courseCode"]
        requested.append(course_number)
        content = COURSE_XML.replace(b"02452", course_number.encode())
        return httpx.Response(200, content=content)

    summary, failures = asyncio.run(
        download_course_information(
            ["01001", "02452"],
            year_group="2026/2027",
            output_directory=tmp_path,
            concurrency=2,
            request_delay=0,
            transport=httpx.MockTransport(handler),
        )
    )

    assert requested == ["01001", "02452"]
    assert (tmp_path / "01001.txt").is_file()
    assert (tmp_path / "02452.txt").read_bytes() == COURSE_XML
    assert summary.downloaded == 2
    assert summary.failed == 0
    assert failures == []


def test_skips_an_existing_valid_file(tmp_path):
    (tmp_path / "02452.txt").write_bytes(COURSE_XML)

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    summary, failures = asyncio.run(
        download_course_information(
            ["02452"],
            year_group="2026/2027",
            output_directory=tmp_path,
            request_delay=0,
            transport=httpx.MockTransport(unexpected_request),
        )
    )

    assert summary.skipped == 1
    assert failures == []
