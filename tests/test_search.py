from unittest.mock import patch

from app.config import get_settings
from app.services.dtu_keyword_search_service import DtuKeywordSearchError


def test_search_matches_content_and_is_compact(client, auth_headers, sample_courses):
    response = client.get("/api/v1/courses/search?q=machine%20learning", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["courses"][0]["courseNumber"] == "02450"
    assert "learningObjectives" not in body["courses"][0]
    assert body["courses"][0]["relevanceScore"] is not None


def test_structured_filters(client, auth_headers, sample_courses):
    response = client.get(
        "/api/v1/courses/search?ects=5&level=MSc&period=E&schedule=E2A&department=Compute&language=English&campus=Lyngby",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert [course["courseNumber"] for course in response.json()["courses"]] == ["02450"]


def test_limit_is_capped_at_50(client, auth_headers):
    response = client.get("/api/v1/courses/search?limit=51", headers=auth_headers)
    assert response.status_code == 422


def test_default_academic_year_excludes_old_version(client, auth_headers, sample_courses):
    response = client.get("/api/v1/courses/search?q=machine", headers=auth_headers)
    assert response.json()["count"] == 1


def test_danish_search_uses_only_danish_course_text(client, auth_headers, sample_courses):
    danish = client.get(
        "/api/v1/courses/search?q=beslutningstræer&search_language=da",
        headers=auth_headers,
    )
    english = client.get(
        "/api/v1/courses/search?q=beslutningstræer&search_language=en",
        headers=auth_headers,
    )

    assert [course["courseNumber"] for course in danish.json()["courses"]] == ["02450"]
    assert danish.json()["courses"][0]["title"] == "Introduktion til maskinlæring"
    assert english.json()["count"] == 0


def test_english_search_uses_only_english_course_text(client, auth_headers, sample_courses):
    english = client.get(
        "/api/v1/courses/search?q=decision%20trees&search_language=en",
        headers=auth_headers,
    )
    danish = client.get(
        "/api/v1/courses/search?q=decision%20trees&search_language=da",
        headers=auth_headers,
    )

    assert [course["courseNumber"] for course in english.json()["courses"]] == ["02450"]
    assert english.json()["courses"][0]["title"] == "Introduction to Machine Learning"
    assert danish.json()["count"] == 0


def test_dtu_candidates_broaden_multi_term_search(client, auth_headers, sample_courses):
    settings = get_settings().model_copy(update={"dtu_keyword_search_enabled": True})
    with (
        patch("app.services.search_service.get_settings", return_value=settings),
        patch(
            "app.services.search_service.get_dtu_keyword_course_numbers",
            return_value=["02450", "01418", "99999"],
        ) as provider,
    ):
        response = client.get(
            "/api/v1/courses/search?q=machine%20physics&search_language=en",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [course["courseNumber"] for course in response.json()["courses"]] == [
        "02450",
        "01418",
    ]
    provider.assert_called_once_with("machine physics", "2026-2027")


def test_structured_filters_apply_to_dtu_candidates(client, auth_headers, sample_courses):
    settings = get_settings().model_copy(update={"dtu_keyword_search_enabled": True})
    with (
        patch("app.services.search_service.get_settings", return_value=settings),
        patch(
            "app.services.search_service.get_dtu_keyword_course_numbers",
            return_value=["02450", "01418"],
        ),
    ):
        response = client.get(
            "/api/v1/courses/search?q=machine%20physics&level=MSc&search_language=en",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert [course["courseNumber"] for course in response.json()["courses"]] == ["02450"]


def test_dtu_failure_falls_back_to_local_search(client, auth_headers, sample_courses):
    settings = get_settings().model_copy(update={"dtu_keyword_search_enabled": True})
    with (
        patch("app.services.search_service.get_settings", return_value=settings),
        patch(
            "app.services.search_service.get_dtu_keyword_course_numbers",
            side_effect=DtuKeywordSearchError("unavailable"),
        ),
    ):
        response = client.get(
            "/api/v1/courses/search?q=machine%20learning&search_language=en",
            headers=auth_headers,
        )

    assert response.status_code == 200
    assert [course["courseNumber"] for course in response.json()["courses"]] == ["02450"]


def test_course_listing_does_not_call_dtu_keyword_search(
    client, auth_headers, sample_courses
):
    settings = get_settings().model_copy(update={"dtu_keyword_search_enabled": True})
    with (
        patch("app.services.search_service.get_settings", return_value=settings),
        patch("app.services.search_service.get_dtu_keyword_course_numbers") as provider,
    ):
        response = client.get("/api/v1/courses", headers=auth_headers)

    assert response.status_code == 200
    provider.assert_not_called()
