from unittest.mock import patch

import httpx
import pytest

from app.config import Settings
from app.services.dtu_keyword_search_service import (
    DtuKeywordSearchError,
    clear_dtu_keyword_search_cache,
    fetch_dtu_keyword_course_numbers,
    get_dtu_keyword_course_numbers,
    parse_keyword_search_response,
)


SEARCH_RESPONSE = b"""<?xml version="1.0" encoding="utf-8"?>
<root>
  <Courses CourseCatalogVersion="2026/2027">
    <XMLList>
      <CourseList CourseID="1" CourseCode="02450" volume="2026/2027" />
    </XMLList>
  </Courses>
  <Courses CourseCatalogVersion="2026/2027">
    <XMLList>
      <CourseList CourseID="2" CourseCode="02450" volume="2026/2027" />
      <CourseList CourseID="3" CourseCode="BAD!" volume="2026/2027" />
      <CourseList CourseID="4" CourseCode="01418" volume="2025/2026" />
    </XMLList>
  </Courses>
</root>
"""


def _settings(**updates) -> Settings:
    return Settings(api_key="test-secret").model_copy(update=updates)


def test_fetch_keyword_candidates_sends_complete_dtu_request():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(
            "/coursewebservicev2/course.asmx/SearchDtuShb_Full"
        )
        assert request.url.params["searchWords"] == "kunstig intelligens"
        assert request.url.params["CourseCatalogVersion"] == "2026/2027"
        assert request.url.params["resultType"] == "XMLList"
        assert request.url.params["courseCode"] == ""
        assert request.url.params["textStudieboksen"] == ""
        return httpx.Response(200, content=SEARCH_RESPONSE)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_dtu_keyword_course_numbers(
            "  kunstig   intelligens  ",
            "2026-2027",
            settings=_settings(),
            client=client,
        )

    assert result == ["02450"]


def test_parser_rejects_invalid_xml_and_years():
    with pytest.raises(DtuKeywordSearchError, match="valid XML"):
        parse_keyword_search_response(
            b"<not-closed>", academic_year="2026-2027", max_candidates=20
        )
    with pytest.raises(DtuKeywordSearchError, match="consecutive years"):
        parse_keyword_search_response(
            SEARCH_RESPONSE, academic_year="2026-2028", max_candidates=20
        )


def test_fetch_wraps_http_failures():
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(503, content=b"unavailable")
    )
    with httpx.Client(transport=transport) as client:
        with pytest.raises(DtuKeywordSearchError, match="request failed"):
            fetch_dtu_keyword_course_numbers(
                "machine learning",
                "2026-2027",
                settings=_settings(),
                client=client,
            )


def test_keyword_results_are_cached():
    clear_dtu_keyword_search_cache()
    settings = _settings(dtu_keyword_cache_ttl=60)
    with (
        patch(
            "app.services.dtu_keyword_search_service.get_settings",
            return_value=settings,
        ),
        patch(
            "app.services.dtu_keyword_search_service.fetch_dtu_keyword_course_numbers",
            return_value=["02450"],
        ) as fetch,
    ):
        first = get_dtu_keyword_course_numbers("Machine Learning", "2026-2027")
        second = get_dtu_keyword_course_numbers(" machine  learning ", "2026-2027")

    assert first == second == ["02450"]
    fetch.assert_called_once()
    clear_dtu_keyword_search_cache()
