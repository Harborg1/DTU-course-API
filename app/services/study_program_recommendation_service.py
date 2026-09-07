import re
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.specialization import StudySpecialization
from app.models.study_plan import StudyPlanSection, StudyProgram


_TOKEN_PATTERN = re.compile(r"[a-zæøå0-9]+")

_SEARCH_STOP_WORDS = {
    "about",
    "and",
    "for",
    "inden",
    "interest",
    "interesse",
    "interested",
    "kan",
    "lide",
    "mig",
    "med",
    "og",
    "om",
    "program",
    "programme",
    "relateret",
    "study",
    "til",
}

_TOPIC_EXPANSIONS = {
    "artificial intelligence": {"artificial", "intelligence", "ai", "kunstig", "intelligens"},
    "bæredygtighed": {"bæredygtig", "bæredygtighed", "sustainability", "sustainable"},
    "biotechnology": {"biotech", "biotechnology", "bioteknologi", "biological"},
    "bioteknologi": {"biotech", "biotechnology", "bioteknologi", "biological"},
    "chemistry": {"chemical", "chemistry", "kemi", "kemisk"},
    "energy": {"energy", "energi", "renewable", "bæredygtig"},
    "fysik": {"fysik", "physics", "physical"},
    "kunstig intelligens": {"artificial", "intelligence", "ai", "kunstig", "intelligens"},
    "kemi": {"chemical", "chemistry", "kemi", "kemisk"},
    "machine learning": {"machine", "learning", "maskinlæring", "maskinlearning"},
    "matematik": {"math", "mathematical", "mathematics", "matematik", "matematisk"},
    "mathematics": {"math", "mathematical", "mathematics", "matematik", "matematisk"},
    "physics": {"fysik", "physics", "physical"},
    "software": {"computer", "computing", "software", "softwareteknologi"},
}


@dataclass(frozen=True)
class StudyProgramMatch:
    program: StudyProgram
    score: float
    reason: str


def _tokens(value: str | None) -> set[str]:
    return set(_TOKEN_PATTERN.findall((value or "").casefold()))


def _topic_terms(topic: str) -> set[str]:
    normalized = re.sub(r"\s+", " ", topic.casefold()).strip()
    expanded = set(_TOPIC_EXPANSIONS.get(normalized, set()))
    expanded.update(token for token in _tokens(normalized) if token not in _SEARCH_STOP_WORDS)
    return {term for term in expanded if len(term) >= 2}


def _matches(value: str | None, terms: set[str]) -> bool:
    value_tokens = _tokens(value)
    return bool(value_tokens & terms)


def _short_introduction(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip()
    return cleaned if len(cleaned) <= 320 else cleaned[:317].rstrip() + "..."


def _reason(
    *,
    topic: str,
    language: str,
    name_match: bool,
    profile_match: bool,
    specialization_matches: int,
    course_matches: int,
) -> str:
    if language == "da":
        if name_match:
            return f"Programmets navn og faglige profil matcher din interesse for {topic}."
        if specialization_matches:
            return (
                f"Programmet har {specialization_matches} importeret specialisering, der matcher {topic}."
                if specialization_matches == 1
                else f"Programmet har {specialization_matches} importerede specialiseringer, der matcher {topic}."
            )
        if profile_match:
            return f"Programmets officielle beskrivelse og studieplan matcher din interesse for {topic}."
        return (
            f"{course_matches} importeret kursus i studieplanen matcher {topic}."
            if course_matches == 1
            else f"{course_matches} importerede kurser i studieplanen matcher {topic}."
        )

    if name_match:
        return f"The programme name and academic profile match your interest in {topic}."
    if specialization_matches:
        noun = "specialization" if specialization_matches == 1 else "specializations"
        return f"The programme has {specialization_matches} imported {noun} matching {topic}."
    if profile_match:
        return f"The official programme description and study plan match your interest in {topic}."
    noun = "course" if course_matches == 1 else "courses"
    return f"{course_matches} imported study-plan {noun} match {topic}."


def recommend_study_programs(
    session: Session,
    *,
    topic: str,
    academic_year: str,
    degree_type: str | None = None,
    language: str = "en",
    limit: int = 5,
) -> list[StudyProgramMatch]:
    """Rank imported study programmes using their official structured content."""
    terms = _topic_terms(topic)
    if not terms:
        return []

    start_year = int(academic_year[:4])
    year_filter = or_(
        StudyProgram.academic_year == academic_year,
        and_(
            StudyProgram.academic_year.is_(None),
            or_(StudyProgram.valid_from_year.is_(None), StudyProgram.valid_from_year <= start_year),
            or_(StudyProgram.valid_to_year.is_(None), StudyProgram.valid_to_year >= start_year),
        ),
    )
    filters = [year_filter]
    if degree_type:
        filters.append(StudyProgram.degree_type == degree_type)

    statement = (
        select(StudyProgram)
        .where(*filters)
        .options(
            selectinload(StudyProgram.sections).selectinload(StudyPlanSection.courses),
            selectinload(StudyProgram.specializations).selectinload(StudySpecialization.courses),
        )
    )
    programmes = list(session.scalars(statement).unique())
    matches: list[StudyProgramMatch] = []

    for program in programmes:
        name_match = _matches(program.name, terms) or _matches(program.slug.replace("-", " "), terms)
        alias_match = any(_matches(alias, terms) for alias in program.aliases or [])
        introduction_match = _matches(program.introduction, terms)
        specialization_matches = sum(
            1
            for specialization in program.specializations
            if _matches(specialization.name, terms) or _matches(specialization.description, terms)
        )
        course_matches = sum(
            1
            for section in program.sections
            for course in section.courses
            if _matches(course.title, terms)
        )
        section_matches = sum(
            1
            for section in program.sections
            if _matches(section.name, terms) or _matches(section.description, terms)
        )

        score = (
            (12 if name_match else 0)
            + (9 if alias_match else 0)
            + (4 if introduction_match else 0)
            + min(specialization_matches, 3) * 3
            + min(section_matches, 3) * 2
            + min(course_matches, 8)
        )
        if score <= 0:
            continue
        matches.append(
            StudyProgramMatch(
                program=program,
                score=score,
                reason=_reason(
                    topic=topic,
                    language=language,
                    name_match=name_match or alias_match,
                    profile_match=introduction_match or bool(section_matches),
                    specialization_matches=specialization_matches,
                    course_matches=course_matches,
                ),
            )
        )

    matches.sort(key=lambda item: (-item.score, item.program.name.casefold()))
    return matches[: max(1, limit)]


def study_program_description(program: StudyProgram) -> str | None:
    return _short_introduction(program.introduction)
