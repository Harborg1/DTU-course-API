import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from bs4 import BeautifulSoup, Tag

from app.schemas.course import CourseData

SPACE_RE = re.compile(r"\s+")
SCHEDULE_RE = re.compile(r"\b(?:E|F|J)[1-9][AB]?\b", re.IGNORECASE)


def clean_text(value: str | Tag | None) -> str | None:
    if value is None:
        return None
    text = value.get_text(" ", strip=True) if isinstance(value, Tag) else value
    text = SPACE_RE.sub(" ", text.replace("\xad", "").replace("\u200b", "")).strip()
    return text or None


def _table_values(root: Tag) -> dict[str, str]:
    values: dict[str, str] = {}
    for row in root.select("table tr"):
        label = row.select_one("td label")
        cells = row.find_all("td", recursive=False)
        if label is None or len(cells) < 2:
            continue
        key = clean_text(label)
        value = clean_text(cells[1])
        if key and value:
            values[key.casefold()] = value
    return values


def _section_values(root: Tag) -> dict[str, str]:
    values: dict[str, str] = {}
    content_box = root.select_one(".col-md-6:nth-of-type(2) .box")
    if content_box is None:
        boxes = root.select(".box:not(.information)")
        content_box = boxes[0] if boxes else None
    if content_box is None:
        return values
    for bar in content_box.select(":scope > .bar"):
        fragments: list[str] = []
        for sibling in bar.next_siblings:
            if isinstance(sibling, Tag) and "bar" in sibling.get("class", []):
                break
            text = clean_text(sibling) if isinstance(sibling, (Tag, str)) else None
            if text:
                fragments.append(text)
        key = clean_text(bar)
        value = clean_text(" ".join(fragments))
        if key and value:
            values[key.casefold()] = value
    return values


def _first(values: dict[str, str], *labels: str) -> str | None:
    for label in labels:
        if value := values.get(label.casefold()):
            return value
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    months = {
        "januar": 1, "februar": 2, "marts": 3, "april": 4, "maj": 5, "juni": 6,
        "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
        "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
        "october": 10,
    }
    match = re.search(r"(\d{1,2})\.?(?:\s+)([A-Za-zæøåÆØÅ]+),?\s+(\d{4})", value)
    if not match or match.group(2).casefold() not in months:
        return None
    return datetime(int(match.group(3)), months[match.group(2).casefold()], int(match.group(1)), tzinfo=UTC)


def _normalize_language(value: str | None) -> str | None:
    if value is None:
        return None
    exact = {
        "dansk": "Danish",
        "engelsk": "English",
        "dansk og engelsk": "Danish and English",
        "danish": "Danish",
        "english": "English",
    }
    return exact.get(value.casefold(), value)


def _derive_level(course_type: str | None) -> str | None:
    if not course_type:
        return None
    normalized = course_type.casefold()
    mappings = (("bachelor", "BSc"), ("kandidat", "MSc"), ("master", "MSc"), ("ph.d", "PhD"), ("phd", "PhD"))
    for prefix, level in mappings:
        if normalized.startswith(prefix):
            return level
    return course_type.split(" ", 1)[0]


def _derive_period(schedule: str | None) -> str | None:
    if not schedule:
        return None
    values = []
    normalized = schedule.casefold()
    word_periods = (("efterår", "E"), ("autumn", "E"), ("forår", "F"), ("spring", "F"), ("januar", "J"), ("january", "J"))
    for word, period in word_periods:
        if word in normalized and period not in values:
            values.append(period)
    for match in SCHEDULE_RE.finditer(schedule):
        period = match.group(0)[0].upper()
        if period not in values:
            values.append(period)
    return ",".join(values) or None


def parse_course_page(html: str, course_number: str, academic_year: str, base_url: str = "https://kurser.dtu.dk") -> CourseData:
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#pagecontents")
    if root is None:
        raise ValueError("DTU course content (#pagecontents) was not found")

    headings = root.select("h2")
    if len(headings) < 2:
        raise ValueError("DTU course heading or academic year was not found")
    heading = clean_text(headings[0]) or ""
    displayed_year = (clean_text(headings[1]) or "").replace("/", "-")
    if displayed_year != academic_year:
        raise ValueError(f"expected academic year {academic_year}, found {displayed_year or 'none'}")
    if not heading.upper().startswith(course_number.upper()):
        raise ValueError(f"expected course {course_number}, found heading {heading!r}")
    title_da = heading[len(course_number):].strip(" -")
    if not title_da:
        raise ValueError("DTU course title was empty")

    table = _table_values(root)
    sections = _section_values(root)
    english_title = _first(table, "Engelsk titel", "English title")
    language = _normalize_language(_first(table, "Undervisningssprog", "Language of instruction"))
    ects_text = _first(table, "Point( ECTS )", "Points ( ECTS )", "ECTS")
    try:
        ects = Decimal(ects_text.replace(",", ".")) if ects_text else None
    except InvalidOperation as exc:
        raise ValueError(f"invalid ECTS value: {ects_text}") from exc
    course_type = _first(table, "Kursustype", "Course type")
    level = _derive_level(course_type)
    schedule = _first(table, "Skemaplacering", "Schedule placement")
    department_raw = _first(table, "Institut", "Department")
    department_match = re.match(r"([A-Z0-9]+)\s+(.+)", department_raw or "")
    department_code = department_match.group(1) if department_match else None
    department = department_match.group(2) if department_match else department_raw
    exam_parts = [
        _first(table, "Eksamensplacering", "Exam location"),
        _first(table, "Eksamensvarighed", "Duration of Exam"),
        _first(table, "Hjælpemidler", "Aid"),
    ]
    exam = clean_text("; ".join(part for part in exam_parts if part))
    responsible = _first(table, "Kursusansvarlig", "Course responsible")
    teachers = _first(table, "Medansvarlige", "Co-responsible")

    return CourseData(
        course_number=course_number.upper(), academic_year=academic_year,
        title=english_title or title_da, title_da=title_da, title_en=english_title,
        ects=ects, level=level, course_type=course_type, language=language,
        department=department, department_code=department_code,
        period=_derive_period(schedule), schedule=schedule,
        campus=_first(table, "Undervisningens placering", "Location"),
        prerequisites=_first(table, "Faglige forudsætninger", "Academic prerequisites"),
        mandatory_prerequisites=_first(table, "Obligatoriske forudsætninger", "Mandatory prerequisites"),
        exam=exam, evaluation=_first(table, "Evalueringsform", "Evaluation form", "Bedømmelsesform"),
        description=_first(sections, "Overordnede kursusmål", "General course objectives"),
        content=_first(sections, "Kursusindhold", "Course content"),
        learning_objectives=_first(sections, "Læringsmål", "Learning objectives"),
        course_responsible=responsible, teachers=teachers,
        registration_requirements=_first(table, "Tilmelding", "Registration"),
        remarks=_first(sections, "Bemærkninger", "Remarks"),
        source_url=f"{base_url.rstrip('/')}/course/{academic_year}/{course_number.upper()}",
        source_last_updated=_parse_date(_first(sections, "Sidst opdateret", "Last updated")),
    )
