def test_get_course_returns_complete_course(client, auth_headers, sample_courses):
    response = client.get("/api/v1/courses/02450", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["courseNumber"] == "02450"
    assert body["academicYear"] == "2026-2027"
    assert body["sourceUrl"].endswith("/2026-2027/02450")


def test_get_course_404(client, auth_headers):
    response = client.get("/api/v1/courses/99999", headers=auth_headers)
    assert response.status_code == 404


def test_get_course_honours_academic_year(client, auth_headers, sample_courses):
    response = client.get(
        "/api/v1/courses/02450?academic_year=2025-2026", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Old Machine Learning"


def test_list_pagination(client, auth_headers, sample_courses):
    first = client.get("/api/v1/courses?limit=1", headers=auth_headers).json()
    second = client.get("/api/v1/courses?limit=1&offset=1", headers=auth_headers).json()
    assert first["count"] == 2
    assert len(first["courses"]) == 1
    assert first["courses"][0]["courseNumber"] != second["courses"][0]["courseNumber"]


def test_import_status(client, auth_headers, sample_courses, db_session):
    from datetime import UTC, datetime
    from app.models.import_run import ImportRun

    completed_at = datetime.now(UTC)
    db_session.add(
        ImportRun(
            academic_year="2026-2027",
            status="completed",
            completed_at=completed_at,
            courses_discovered=2,
            courses_imported=2,
        )
    )
    db_session.commit()
    response = client.get("/api/v1/import/status", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["courseCount"] == 2
    assert response.json()["lastSuccessfulImport"] is not None


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "academicYear": "2026-2027"}
