from pathlib import Path

import httpx
import pytest

from scripts.get_all_course_numbers import (
    get_all_course_numbers,
    normalize_catalog_version,
    parse_course_numbers,
    parse_start_letters,
)


FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_and_sorts_course_code_prefixes():
    xml = (FIXTURES / "course_code_prefixes.xml").read_text()
    assert parse_start_letters(xml) == ["01", "02", "KU"]


def test_parses_and_deduplicates_course_numbers():
    xml = (FIXTURES / "courses_by_prefix.xml").read_text()
    assert parse_course_numbers(xml) == {"02002", "02138"}


@pytest.mark.parametrize("value", ["2026/2027", "2026-2027"])
def test_normalizes_catalog_version(value):
    assert normalize_catalog_version(value) == "2026/2027"


def test_rejects_invalid_catalog_version():
    with pytest.raises(ValueError, match="catalog version"):
        normalize_catalog_version("2026/2028")


def test_fetches_every_prefix_and_returns_sorted_unique_numbers():
    requested_prefixes: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/GetCourseCodeStartLetters"):
            return httpx.Response(
                200,
                text='<root><Course startLetters="02"/><Course startLetters="01"/></root>',
            )
        requested_prefixes.append(request.url.params["letters"])
        course_number = "02452" if request.url.params["letters"] == "02" else "01001"
        return httpx.Response(
            200,
            text=f'<root><CourseList CourseCode="{course_number}"/></root>',
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = get_all_course_numbers(
            "2026-2027",
            client=client,
            request_delay=0,
        )

    assert requested_prefixes == ["01", "02"]
    assert result == ["01001", "02452"]
