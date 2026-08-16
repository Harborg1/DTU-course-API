from app.services.recommendation_service import understand_context


def test_understands_natural_language_student_context():
    context = understand_context(
        ["Jeg studerer Computer Science and Engineering på MSc niveau og vil gerne have kurser inden for machine learning"]
    )

    assert context.topic == "machine learning"
    assert context.level == "MSc"


def test_understands_optional_course_filters():
    context = understand_context(["Find et engelsksproget BSc-kursus på 5 ECTS i periode E om optimization"])

    assert context.topic == "optimization"
    assert context.level == "BSc"
    assert float(context.ects) == 5
    assert context.language == "English"
    assert context.period == "E"


def test_understands_danish_software_technology_prompt():
    context = understand_context(
        ["Jeg læser BSc software teknologi og vil gerne have kurser i softwareteknologi"]
    )

    assert context.topic == "software technology"
    assert context.level == "BSc"


def test_public_chat_recommends_matching_course_without_api_key(client, sample_courses):
    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Jeg læser MSc og søger kurser inden for machine learning",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["understood"]["topic"] == "machine learning"
    assert body["understood"]["level"] == "MSc"
    assert [course["courseNumber"] for course in body["recommendations"]] == ["02450"]
    assert body["recommendations"][0]["sourceUrl"].startswith("https://kurser.dtu.dk/")


def test_chat_requires_a_user_message(client):
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "assistant", "content": "Hvordan kan jeg hjælpe?"}]},
    )

    assert response.status_code == 422


def test_chat_returns_clear_empty_result(client):
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Jeg vil lære biotechnology"}]},
    )

    assert response.status_code == 200
    assert response.json()["recommendations"] == []
    assert "ikke finde" in response.json()["reply"]
