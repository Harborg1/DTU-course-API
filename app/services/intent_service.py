import re
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Intent:
    type: str
    confidence: float = 0.0


@dataclass
class CourseQAIntent(Intent):
    type: str = "course_qa"
    course_number: str = ""


@dataclass
class StudyPlanIntent(Intent):
    type: str = "study_plan_qa"
    program_name: str = ""
    degree_type: str = ""
    query_keywords: list[str] = field(default_factory=list)
    requires_ects_calculation: bool = False
    requires_course_count: bool = False
    requires_section_info: bool = False


@dataclass
class RecommendationIntent(Intent):
    type: str = "course_recommendation"
    topic: str = ""
    level: str = ""
    ects: float = 0.0
    language: str = ""
    period: str = ""


@dataclass
class OpenQuestionIntent(Intent):
    type: str = "open_question"


_STUDY_PLAN_INDICATORS = [
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
    "opbygget",
    "opbyggelse",
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
    "hvordan skal jeg",
    "hvornår må jeg",
    "skal jeg have",
    "must i have",
    "should i take",
    "hvor mange ects",
    "how many ects",
    "hvordan er uddannelsen",
    "how is the programme",
    "hvilke valgfrie",
    "which electives",
    "hvad er programme-specific",
    "hvad er programmespecifikke",
    "hvad er valgfrie kurser",
    "hvordan ser studieplanen ud",
    "what is the study plan",
    "how is the curriculum structured",
    "can you tell me about",
    "tell me about the programme",
    "what courses are required",
    "hvad er kurserne i",
    "study programme structure",
    "hvordan er kurserne organiseret",
    "hvilke fag",
    "which subjects",
    "hvordan er optagelseskrav",
    "what are the admission requirements",
]

_INTENT_KEYWORDS = {
    "ects": {
        "ects",
        "point",
        "credit",
        "credit points",
        "studiepoint",
        "studiepoints",
        "ects-point",
        "studiepoint",
    },
    "programme-specific": {
        "programme-specific",
        "program-specific",
        "programmespecifik",
        "programspecifik",
        "retningsspecifik",
    },
    "bachelor": {
        "bsc",
        "bachelor",
        "bachelorstudie",
        "bacheloruddannelse",
    },
    "master": {
        "msc",
        "master",
        "kandidat",
        "kandidatstudie",
        "kandidatuddannelse",
    },
    "mandatory": {
        "obligatorisk",
        "compulsory",
        "mandatory",
        "skal tage",
        "skal have",
        "must take",
        "required",
    },
    "elective": {
        "valgfri",
        "elective",
        "frivillig",
        "valgfrie",
        "electives",
        "valgfrie kurser",
    },
    "project": {
        "projekt",
        "project",
        "speciale",
        "thesis",
        "afhandling",
        "master thesis",
        "bachelor project",
    },
    "structure": {
        "opbygning",
        "structure",
        "curriculum",
        "studieplan",
        "studieordning",
        "program structure",
        "programme structure",
    },
    "requirement": {
        "krav",
        "requirement",
        "requirements",
        "regler",
        "rules",
        "forudsætning",
        "prerequisite",
    },
    "topic": {
        "maskinlærning",
        "maskinlearning",
        "machine learning",
        "deep learning",
        "kunstig intelligens",
        "artificial intelligence",
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
    },
}

_COURSE_NUMBER_PATTERN = r"\b(\d{5})\b"


def extract_course_number(text: str) -> str | None:
    """Extract 5-digit course number from text."""
    match = re.search(_COURSE_NUMBER_PATTERN, text)
    return match.group(1) if match else None


def extract_intent_keywords(text: str) -> list[str]:
    """Extract intent keywords from user's question."""
    normalized = text.casefold()
    found_keywords = []

    for intent_key, keywords in _INTENT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in normalized:
                found_keywords.append(intent_key)
                break

    return found_keywords


def extract_topic(text: str) -> str:
    """Return the final explicitly named recommendation topic."""
    normalized = text.casefold()
    matches = [
        (normalized.rfind(topic), topic)
        for topic in _INTENT_KEYWORDS["topic"]
        if topic in normalized
    ]
    return max(matches)[1] if matches else ""


def is_study_plan_related(text: str) -> bool:
    """Check if text is about study program rules/requirements."""
    normalized = text.casefold()
    return any(indicator in normalized for indicator in _STUDY_PLAN_INDICATORS)


def classify_intent(text: str) -> Intent:
    """Classify user's intent based on their question.

    Priority order:
    1. Course Q&A — 5-digit course number
    2. Study Plan Q&A — study program rules/requirements
    3. Course Recommendation — topic/level/ects search
    4. Open Question — general question
    """
    course_number = extract_course_number(text)
    keywords = extract_intent_keywords(text)

    if course_number:
        return CourseQAIntent(confidence=1.0, course_number=course_number)

    if is_study_plan_related(text):
        requires_ects = any(kw in keywords for kw in ["ects", "point", "credit"])
        requires_course_count = any(kw in keywords for kw in ["mandatory", "elective"])
        requires_section = any(kw in keywords for kw in ["programme-specific", "project", "bachelor", "master"])

        return StudyPlanIntent(
            confidence=0.8,
            query_keywords=keywords,
            requires_ects_calculation=requires_ects,
            requires_course_count=requires_course_count,
            requires_section_info=requires_section,
        )

    if keywords:
        return RecommendationIntent(
            confidence=0.7,
            topic=extract_topic(text),
            level="MSc" if "master" in keywords else "BSc" if "bachelor" in keywords else "",
        )

    return OpenQuestionIntent(confidence=0.5)
