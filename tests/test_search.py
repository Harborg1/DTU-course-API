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

