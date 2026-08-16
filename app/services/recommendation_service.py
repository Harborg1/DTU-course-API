import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session

from app.models.course import Course
from app.schemas.recommendation import ChatResponse, RecommendedCourse, UnderstoodContext
from app.services.search_service import SearchResult, search_courses


_TOPICS = (
    "machine learning",
    "deep learning",
    "artificial intelligence",
    "kunstig intelligens",
    "computer vision",
    "data science",
    "data engineering",
    "software engineering",
    "software technology",
    "software teknologi",
    "softwareteknologi",
    "cyber security",
    "cybersikkerhed",
    "information security",
    "operations research",
    "natural language processing",
    "robotics",
    "robotteknologi",
    "optimization",
    "optimisation",
    "optimering",
    "algorithms",
    "algoritmer",
    "statistics",
    "statistik",
    "physics",
    "fysik",
    "mathematics",
    "matematik",
    "sustainability",
    "bæredygtighed",
    "biotechnology",
    "bioteknologi",
)

_TOPIC_ALIASES = {
    "kunstig intelligens": "artificial intelligence",
    "cybersikkerhed": "cyber security",
    "robotteknologi": "robotics",
    "optimisation": "optimization",
    "optimering": "optimization",
    "algoritmer": "algorithms",
    "statistik": "statistics",
    "fysik": "physics",
    "matematik": "mathematics",
    "bæredygtighed": "sustainability",
    "bioteknologi": "biotechnology",
    "software technology": "software technology",
    "software teknologi": "software technology",
    "softwareteknologi": "software technology",
}

_STOP_WORDS = {
    "af", "alle", "at", "and", "anbefal", "anbefale", "anbefalet", "are", "course", "courses",
    "der", "det", "du", "eller", "en", "er", "et", "for", "fra", "give", "gerne", "har", "hej",
    "have", "i", "inden", "jeg", "kan", "kursus", "kurser", "læser", "me", "med", "mig", "min", "mit", "niveau",
    "of", "om", "on", "på", "recommend", "show", "som", "studerer", "studere", "study", "til", "vil",
    "want", "within", "you", "please", "find", "looking", "interested", "interesseret", "interesserer", "msc", "bsc",
    "master", "bachelor", "phd", "level", "niveauet", "the", "some", "in", "engineering", "science", "og", "søger", "ønsker",
}


@dataclass(frozen=True)
class RecommendationContext:
    topic: str
    level: str | None
    ects: Decimal | None
    language: str | None
    period: str | None


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()


def _extract_level(text: str) -> str | None:
    if re.search(r"\b(msc|master|kandidat)\b", text):
        return "MSc"
    if re.search(r"\b(bsc|bachelor|diplom)\b", text):
        return "BSc"
    if re.search(r"\b(phd|ph\.d)\b", text):
        return "PhD"
    return None


def _extract_ects(text: str) -> Decimal | None:
    match = re.search(r"\b(\d{1,3}(?:[.,]\d+)?)\s*ects\b", text)
    if not match:
        return None
    try:
        value = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    return value if Decimal("0") < value <= Decimal("120") else None


def _extract_language(text: str) -> str | None:
    if re.search(r"\b(engelsk(?:sproget)?|english)\b", text):
        return "English"
    if re.search(r"\b(dansk(?:sproget)?|danish)\b", text):
        return "Danish"
    return None


def _extract_period(text: str) -> str | None:
    match = re.search(r"\b(?:periode|period)\s+([ef])\b", text)
    if match:
        return match.group(1).upper()
    if "januar" in text or "january" in text or "3-week" in text or "3 week" in text:
        return "January"
    if "juni" in text or "june" in text:
        return "June"
    return None


def _extract_topic(text: str) -> str:
    positions: list[tuple[int, str]] = []
    for topic in _TOPICS:
        for match in re.finditer(rf"\b{re.escape(topic)}\b", text):
            positions.append((match.start(), _TOPIC_ALIASES.get(topic, topic)))
    if positions:
        # The final named subject is commonly the requested specialisation after
        # the student has first described their study programme.
        return max(positions, key=lambda item: item[0])[1]

    tokens = re.findall(r"[a-zæøå0-9][a-zæøå0-9+#.-]{1,}", text)
    useful = [token for token in tokens if token not in _STOP_WORDS and not token.isdigit()]
    return " ".join(useful[-6:]) or "DTU courses"


def understand_context(messages: list[str]) -> RecommendationContext:
    text = _normalise(" ".join(messages))
    return RecommendationContext(
        topic=_extract_topic(text),
        level=_extract_level(text),
        ects=_extract_ects(text),
        language=_extract_language(text),
        period=_extract_period(text),
    )


def _run_search(session: Session, context: RecommendationContext, academic_year: str) -> SearchResult:
    kwargs = {
        "q": None if context.topic == "DTU courses" else context.topic,
        "academic_year": academic_year,
        "ects": context.ects,
        "level": context.level,
        "period": context.period,
        "language": context.language,
        "limit": 5,
        "offset": 0,
    }
    result = search_courses(session, **kwargs)
    if result.count == 0 and context.level:
        kwargs["level"] = None
        result = search_courses(session, **kwargs)
    if result.count == 0 and context.ects:
        kwargs["ects"] = None
        result = search_courses(session, **kwargs)
    return result


def _reason(course: Course, context: RecommendationContext) -> str:
    reasons = [f"Kursets indhold matcher emnet {context.topic}"]
    if context.level and course.level and context.level.casefold() in course.level.casefold():
        reasons.append(f"det er angivet på {course.level}-niveau")
    if context.ects is not None and course.ects == context.ects:
        reasons.append(f"det giver {float(course.ects):g} ECTS")
    if context.language and course.language == context.language:
        reasons.append(f"undervisningssproget er {course.language}")
    return ", og ".join(reasons) + "."


def recommend_courses(
    session: Session,
    *,
    messages: list[str],
    academic_year: str,
) -> ChatResponse:
    context = understand_context(messages)
    result = _run_search(session, context, academic_year)
    ranked_courses = result.courses
    if ranked_courses and ranked_courses[0][1] > 0:
        minimum_score = ranked_courses[0][1] * 0.4
        ranked_courses = [item for item in ranked_courses if item[1] >= minimum_score]
    courses = [
        RecommendedCourse(
            courseNumber=course.course_number,
            title=course.title,
            ects=float(course.ects) if course.ects is not None else None,
            level=course.level,
            period=course.period,
            schedule=course.schedule,
            language=course.language,
            department=course.department,
            description=(course.description[:357].rstrip() + "...")
            if course.description and len(course.description) > 360
            else course.description,
            reason=_reason(course, context),
            sourceUrl=course.source_url,
        )
        for course, _score in ranked_courses
    ]
    understood = UnderstoodContext(
        topic=context.topic,
        level=context.level,
        ects=float(context.ects) if context.ects is not None else None,
        language=context.language,
        period=context.period,
    )
    if courses:
        qualifiers = [context.topic]
        if context.level:
            qualifiers.append(f"{context.level}-niveau")
        reply = (
            f"Jeg fandt {len(courses)} relevante kurser til "
            f"{', '.join(qualifiers)}. Se anbefalingerne nedenfor, og kontrollér altid "
            "forudsætninger og den aktuelle kursusbeskrivelse via DTU-linket."
        )
    else:
        reply = (
            "Jeg kunne ikke finde kurser, der matcher det endnu. Prøv at skrive et mere konkret "
            "emne, eksempelvis machine learning, optimization eller computer vision."
        )
    return ChatResponse(
        reply=reply,
        understood=understood,
        recommendations=courses,
        academicYear=academic_year,
    )
