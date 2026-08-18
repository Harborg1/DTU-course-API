import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.course import Course
from app.models.study_plan import StudyPlanRequirement, StudyPlanRequirementCourse, StudyPlanSection, StudyProgram
from app.schemas.recommendation import (
    ChatResponse,
    RecommendedCourse,
    StudyPlanCourseInfo,
    StudyPlanOverview,
    StudyPlanRequirementInfo,
    StudyPlanSectionInfo,
    UnderstoodContext,
)
from app.services.search_service import SearchResult, search_courses
from app.services.study_program_aliases import PROGRAM_ALIASES


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

_STUDY_PLAN_TERMS = (
    "obligatorisk",
    "adgangskrav",
    "course requirements",
    "curriculum",
    "degree requirements",
    "hvad er kravene",
    "hvad er reglerne",
    "hvad skal jeg have",
    "hvad skal jeg tage",
    "how is my degree structured",
    "how is my programme structured",
    "how is my program structured",
    "opbygning",
    "program structure",
    "programme structure",
    "programme requirements",
    "program requirements",
    "regler for mit studie",
    "reglerne for mit studie",
    "studieplan",
    "studieordning",
    "study plan",
    "retningsspecifik",
    "polytekniske grundlag",
    "hvilke kurser skal",
    "which courses do i need",
    "which courses must i take",
    "mandatory courses",
    "hvordan er studiet",
    "hvordan studiet er",
    "uddannelsen bygget op",
)


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
    if re.search(r"\b(msc|master(?:'s)?|kandidat(?:en|uddannelse[nr]?)?|civilingeniør|graduate)\b", text):
        return "MSc"
    if re.search(r"\b(bsc|bachelor(?:en|uddannelse[nr]?)?|diplom(?:ingeniør)?)\b", text):
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


def _program_key(value: str) -> str:
    return " ".join(re.findall(r"[a-zæøå0-9]+", value.casefold()))


def _is_study_plan_question(text: str) -> bool:
    folded = _normalise(text)
    return any(term in folded for term in _STUDY_PLAN_TERMS)


def _requested_degree_type(text: str) -> str | None:
    return {"MSc": "Master", "BSc": "Bachelor"}.get(_extract_level(_normalise(text)))


def _program_aliases(program: StudyProgram) -> dict[str, int]:
    aliases: dict[str, int] = {}

    def add(value: str | None, priority: int) -> None:
        if not value:
            return
        key = _program_key(value)
        if key:
            aliases[key] = max(priority, aliases.get(key, 0))

    add(program.name, 40)
    for alias in program.aliases or []:
        add(alias, 35)
    add(program.slug.replace("-", " "), 30)
    for alias in PROGRAM_ALIASES.get(program.slug, ()):
        add(alias, 20)
    return aliases


def _alias_similarity(alias: str, text_tokens: list[str]) -> float:
    alias_tokens = alias.split()
    if len(alias) < 5 or not alias_tokens or len(alias_tokens) > len(text_tokens):
        return 0.0
    window_size = len(alias_tokens)
    return max(
        SequenceMatcher(None, alias, " ".join(text_tokens[index : index + window_size])).ratio()
        for index in range(len(text_tokens) - window_size + 1)
    )


def _matching_study_program(session: Session, text: str) -> StudyProgram | None:
    normalized_key = _program_key(text)
    padded_text = f" {normalized_key} "
    text_tokens = normalized_key.split()
    requested_degree = _requested_degree_type(text)
    programs = list(session.scalars(select(StudyProgram)))
    candidates: list[tuple[int, float, int, int, StudyProgram]] = []

    for program in programs:
        if requested_degree and program.degree_type != requested_degree:
            continue
        for alias, priority in _program_aliases(program).items():
            if f" {alias} " in padded_text:
                candidates.append((2, 1.0, priority, len(alias), program))
                continue
            similarity = _alias_similarity(alias, text_tokens)
            threshold = 0.88 if len(alias.split()) == 1 else 0.84
            if similarity >= threshold:
                candidates.append((1, similarity, priority, len(alias), program))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[:4], reverse=True)
    best = candidates[0]
    competing = next((item for item in candidates[1:] if item[4].id != best[4].id), None)
    if competing is not None:
        if best[0] == competing[0] == 2 and best[1:4] == competing[1:4]:
            return None
        if best[0] == competing[0] == 1 and best[1] - competing[1] < 0.04:
            return None

    statement = select(StudyProgram).where(StudyProgram.id == best[4].id).options(
        selectinload(StudyProgram.sections).selectinload(StudyPlanSection.courses),
        selectinload(StudyProgram.sections)
        .selectinload(StudyPlanSection.requirements)
        .selectinload(StudyPlanRequirement.course_links)
        .selectinload(StudyPlanRequirementCourse.course),
    )
    return session.scalar(statement)


def _study_plan_course_info(course) -> StudyPlanCourseInfo:
    return StudyPlanCourseInfo(
        courseNumber=course.course_number,
        title=course.title,
        ects=float(course.ects) if course.ects is not None else None,
        ectsOptions=course.ects_options or [],
        schedule=course.schedule,
        requirementRole=course.requirement_role,
        sourceUrl=course.source_url,
    )


def _study_plan_overview(program: StudyProgram) -> StudyPlanOverview:
    sections = []
    for section in program.sections:
        requirements = []
        for requirement in section.requirements:
            linked_courses = sorted(
                (link.course for link in requirement.course_links), key=lambda course: course.position
            )
            requirements.append(
                StudyPlanRequirementInfo(
                    requirementType=requirement.requirement_type,
                    description=requirement.description,
                    requiredEcts=float(requirement.required_ects) if requirement.required_ects is not None else None,
                    requiredCount=requirement.required_count,
                    isSubrequirement=requirement.parent_requirement_id is not None,
                    courses=[_study_plan_course_info(course) for course in linked_courses],
                )
            )
        sections.append(
            StudyPlanSectionInfo(
                name=section.name,
                description=section.description,
                courses=[_study_plan_course_info(course) for course in section.courses],
                requirements=requirements,
            )
        )
    return StudyPlanOverview(
        programName=program.name,
        degreeType=program.degree_type,
        academicYear=program.academic_year,
        validFromYear=program.valid_from_year,
        validToYear=program.valid_to_year,
        sourceUrl=program.source_url,
        sections=sections,
    )


def _course_labels(requirement: StudyPlanRequirement) -> str:
    courses = sorted((link.course for link in requirement.course_links), key=lambda course: course.position)
    return ", ".join(
        f"{course.course_number} {course.title}" if course.course_number else course.title for course in courses
    )


def _format_ects(value: Decimal) -> str:
    return f"{float(value):g}"


def _choice_requirement_detail(requirement: StudyPlanRequirement) -> str | None:
    courses = sorted((link.course for link in requirement.course_links), key=lambda course: course.position)
    if not courses:
        return None

    labels = _course_labels(requirement)
    ects_values = {course.ects for course in courses if course.ects is not None}
    common_ects = next(iter(ects_values)) if len(ects_values) == 1 else None
    ects_phrase = f" på {_format_ects(common_ects)} ECTS" if common_ects is not None else ""

    if requirement.requirement_type == "one_of":
        alternative_match = re.search(
            r"alternative to\s+([0-9/\s]+)", requirement.description, flags=re.IGNORECASE
        )
        primary_numbers = set(re.findall(r"\d{5}", alternative_match.group(1))) if alternative_match else set()
        if primary_numbers:
            primary = [course for course in courses if course.course_number in primary_numbers]
            alternatives = [course for course in courses if course.course_number not in primary_numbers]
            if primary and alternatives:
                primary_labels = ", ".join(
                    f"{course.course_number} {course.title}" if course.course_number else course.title
                    for course in primary
                )
                alternative_labels = ", ".join(
                    f"{course.course_number} {course.title}" if course.course_number else course.title
                    for course in alternatives
                )
                return (
                    f"Vælg ét kursus{ects_phrase}: normalt ét blandt {primary_labels}. "
                    "Hvis du har avancerede innovationskompetencer, kan du i stedet vælge ét blandt "
                    f"{alternative_labels}."
                )
        return f"Vælg ét kursus{ects_phrase} blandt: {labels}."

    if requirement.requirement_type == "exact_count" and requirement.required_count is not None:
        note = ""
        if "core competence courses" in requirement.description.casefold():
            leading_text = re.split(
                r"core competence courses", requirement.description, maxsplit=1, flags=re.IGNORECASE
            )[0].strip()
            if leading_text:
                note = f"Bemærk: {leading_text} "
        return f"{note}Vælg præcis {requirement.required_count} kurser blandt: {labels}."

    if requirement.requirement_type == "min_count" and requirement.required_count is not None:
        return f"Vælg mindst {requirement.required_count} kurser blandt: {labels}."

    if requirement.requirement_type == "group_ects" and requirement.required_ects is not None:
        return f"Vælg {_format_ects(requirement.required_ects)} ECTS fra denne pulje: {labels}."

    return None


def _study_plan_reply(program: StudyProgram) -> str:
    validity = f" for studerende optaget fra {program.valid_from_year}" if program.valid_from_year else ""
    lines = [f"Her er opbygningen af {program.name}{validity}:"]
    for section in program.sections:
        details: list[str] = []
        seen_requirement_descriptions: set[str] = set()
        mandatory = [course for course in section.courses if course.requirement_role == "mandatory"]
        if mandatory:
            labels = ", ".join(
                f"{course.course_number} {course.title}" if course.course_number else course.title
                for course in mandatory
            )
            details.append(f"Obligatoriske kurser: {labels}.")
        for requirement in section.requirements:
            if requirement.requirement_type == "all_of":
                continue
            typed_detail = _choice_requirement_detail(requirement)
            if typed_detail:
                details.append(typed_detail)
                continue
            description_key = _normalise(requirement.description)
            if description_key not in seen_requirement_descriptions:
                details.append(requirement.description)
                seen_requirement_descriptions.add(description_key)
        if section.name.casefold() in {"projekter", "projects"} and section.courses:
            if section.description:
                details.append(section.description)
            details.append(
                "Projekter: "
                + ", ".join(
                    f"{course.course_number} {course.title}" if course.course_number else course.title
                    for course in section.courses
                )
                + "."
            )
        if section.name.casefold() == "forhåndsgodkendte kandidatkurser" or (
            "pre-approved" in section.name.casefold() and "msc" in section.name.casefold()
        ):
            details.append(f"Listen indeholder {len(section.courses)} forhåndsgodkendte kandidatkurser.")
        if details:
            lines.append(f"{section.name}: {' '.join(details)}")
    lines.append("Kurser i underkrav tæller samtidig med i den overordnede ECTS-pulje; de tælles ikke dobbelt.")
    return "\n\n".join(lines)


def _answer_study_plan(
    program: StudyProgram,
    *,
    academic_year: str,
) -> ChatResponse:
    return ChatResponse(
        reply=_study_plan_reply(program),
        understood=UnderstoodContext(topic="study plan", level=program.degree_type, program=program.name),
        recommendations=[],
        studyPlan=_study_plan_overview(program),
        academicYear=program.academic_year or academic_year,
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
    conversation = " ".join(messages)
    if _is_study_plan_question(conversation):
        program = _matching_study_program(session, conversation)
        if program is not None:
            return _answer_study_plan(program, academic_year=academic_year)
        return ChatResponse(
            reply=(
                "Jeg kan forklare studieplanen, men jeg kan ikke identificere uddannelsen entydigt. "
                "Skriv både uddannelsens navn og niveau, for eksempel ‘Jeg læser Bioteknologi på kandidaten’."
            ),
            understood=UnderstoodContext(topic="study plan"),
            recommendations=[],
            academicYear=academic_year,
        )
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
