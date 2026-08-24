import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".").strip())
    except InvalidOperation:
        return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


@dataclass
class SpecializationCourseData:
    key: str
    course_number: str | None
    title: str
    ects: Decimal | None
    schedule: str | None
    source_url: str | None
    role: str
    is_terminated: bool
    position: int


@dataclass
class SpecializationRequirementData:
    requirement_type: str
    description: str
    required_ects: Decimal | None = None
    required_count: int | None = None
    member_keys: list[str] = field(default_factory=list)
    position: int = 0


@dataclass
class SpecializationData:
    program_slug: str
    slug: str
    name: str
    description: str | None
    source_url: str
    position: int
    courses: list[SpecializationCourseData] = field(default_factory=list)
    requirements: list[SpecializationRequirementData] = field(default_factory=list)

    def hash_payload(self) -> dict:
        return asdict(self)


_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}

_BOILERPLATE_PREFIXES = (
    "specializations are merely recommended",
    "specialisations are merely recommended",
    "applicants are not admitted",
)


def _url_metadata(source_url: str) -> tuple[str, str | None]:
    parts = [part for part in urlparse(source_url).path.split("/") if part]
    folded = [part.casefold() for part in parts]
    try:
        programme_index = folded.index("msc-programmes")
        specialization_index = folded.index("specialization", programme_index + 1)
        program_slug = folded[programme_index + 1]
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Not a supported DTU specialization URL: {source_url}") from exc
    specialization_slug = folded[specialization_index + 1] if specialization_index + 1 < len(parts) else None
    return program_slug, specialization_slug


def _course_from_row(
    row: Tag,
    *,
    role: str,
    source_url: str,
    position: int,
) -> SpecializationCourseData | None:
    cells = row.find_all("td", recursive=False)
    if len(cells) < 2:
        return None
    link = row.find("a", href=re.compile(r"/course/", re.I))
    if link is None:
        return None
    number_match = re.search(r"\b(?:\d{5}|[A-Z]{2}\d{3})\b", _clean(link.get_text(" ", strip=True)), re.I)
    if number_match is None:
        return None
    course_number = number_match.group(0).upper()
    title = _clean(cells[1].get_text(" ", strip=True))
    if not title:
        return None
    ects_text = _clean(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else ""
    ects_match = re.search(r"\d+(?:[.,]\d+)?", ects_text)
    schedule = _clean(cells[-1].get_text(" ", strip=True)) if len(cells) >= 5 else ""
    return SpecializationCourseData(
        key=course_number,
        course_number=course_number,
        title=title,
        ects=_decimal(ects_match.group(0)) if ects_match else None,
        schedule=schedule or None,
        source_url=urljoin(source_url, str(link.get("href"))),
        role=role,
        is_terminated=False,
        position=position,
    )


def _requirement_metadata(text: str, course_count: int) -> tuple[str, Decimal | None, int | None, str]:
    folded = text.casefold()
    ects_match = re.search(r"at least\s+(\d+(?:[.,]\d+)?)\s+ects", folded)
    if ects_match:
        return "min_ects", _decimal(ects_match.group(1)), None, "choice"

    count_match = re.search(r"at least\s+(one|two|three|four|five|\d+)\s+(?:of\s+the\s+following\s+)?courses?", folded)
    if not count_match:
        count_match = re.search(r"at least\s+(one|two|three|four|five|\d+)\s+of\s+the\s+following", folded)
    if count_match:
        token = count_match.group(1)
        count = int(token) if token.isdigit() else _NUMBER_WORDS[token]
        return "min_count", None, count, "choice"

    if re.search(r"\b(one|1)\s+of\s+the\s+following", folded) or "choose one" in folded:
        return "one_of", None, 1, "choice"
    if "select both" in folded or "both of the following" in folded:
        return "all_of", None, course_count, "mandatory"
    if "recommended" in folded or ("relevant courses" in folded and "not needed" in folded):
        return "recommended", None, None, "recommended"
    if (
        "mandatory" in folded
        or "required for fulfilling" in folded
        or "required for completing" in folded
        or "must take all" in folded
    ):
        return "all_of", None, course_count, "mandatory"

    ects_pool_match = re.search(r"(\d+(?:[.,]\d+)?)\s+ects.*(?:following|these courses|course list)", folded)
    if ects_pool_match:
        return "min_ects", _decimal(ects_pool_match.group(1)), None, "choice"
    return "course_pool", None, None, "choice"


def _description(content: Tag) -> str | None:
    paragraphs: list[str] = []
    for element in content.find_all(["p", "div"], recursive=True):
        if element.find_parent("table") is not None or element.find("table") is not None:
            continue
        text = _clean(element.get_text(" ", strip=True))
        folded = text.casefold()
        if not text or any(folded.startswith(prefix) for prefix in _BOILERPLATE_PREFIXES):
            continue
        if re.search(
            r"\b(?:mandatory|one of the following|select (?:both|at least)|at least \d+(?:[.,]\d+)? ects|"
            r"courses? (?:are|is) recommended|required for fulfilling|example study plans?)\b",
            folded,
        ):
            break
        if text not in paragraphs:
            paragraphs.append(text)
        if len(paragraphs) == 3:
            break
    return "\n".join(paragraphs) or None


def _contextual_tables(content: Tag) -> list[tuple[Tag, str]]:
    tables: list[tuple[Tag, str]] = []
    pending: list[str] = []
    in_examples = False
    for element in content.find_all(["h2", "h3", "h4", "p", "table"], recursive=True):
        if element.find_parent("table") is not None:
            continue
        if element.name == "table":
            if not in_examples and element.find("a", href=re.compile(r"/course/", re.I)) is not None:
                tables.append((element, " ".join(pending[-3:])))
            pending = []
            continue
        text = _clean(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name in {"h2", "h3", "h4"} and "example study plan" in text.casefold():
            in_examples = True
            continue
        if not in_examples:
            pending.append(text)
    return tables


def _terminated_courses(content: Tag, source_url: str, start_position: int) -> list[SpecializationCourseData]:
    courses: list[SpecializationCourseData] = []
    for paragraph in content.find_all("p"):
        text = _clean(paragraph.get_text(" ", strip=True))
        if "terminated course" not in text.casefold():
            continue
        for match in re.finditer(
            r"\b(\d{5})\s+(.+?)\s+\((\d+(?:[.,]\d+)?)\s+ECTS\)",
            text,
            flags=re.I,
        ):
            number, title, ects = match.groups()
            title = re.sub(r"^(?:and|or)\s+", "", title.strip(" ,.;"), flags=re.I)
            courses.append(
                SpecializationCourseData(
                    key=f"terminated:{number}",
                    course_number=number,
                    title=title,
                    ects=_decimal(ects),
                    schedule=None,
                    source_url=urljoin(source_url, f"https://kurser.dtu.dk/course/{number}"),
                    role="historical",
                    is_terminated=True,
                    position=start_position + len(courses),
                )
            )
    return courses


def _multi_specialization_page(
    content: Tag,
    *,
    program_slug: str,
    source_url: str,
) -> list[SpecializationData]:
    names: list[str] = []
    for listing in content.find_all(["ol", "ul"]):
        candidates = [_clean(item.get_text(" ", strip=True)) for item in listing.find_all("li", recursive=False)]
        candidates = [name for name in candidates if name and len(name) <= 80]
        if len(candidates) >= 2:
            names = candidates
            break
    if not names:
        raise ValueError("Specialization overview page contains no specialization names")

    page_text = _clean(content.get_text(" ", strip=True))
    ects_match = re.search(r"fulfilled.*?(\d+(?:[.,]\d+)?)\s+ECTS", page_text, flags=re.I)
    required_ects = _decimal(ects_match.group(1)) if ects_match else None
    description = _description(content)
    result = []
    for position, name in enumerate(names):
        requirements = []
        if required_ects is not None:
            requirements.append(
                SpecializationRequirementData(
                    requirement_type="min_ects",
                    description=f"Fulfil {required_ects:g} ECTS within the recommended courses for this specialization.",
                    required_ects=required_ects,
                    position=0,
                )
            )
        result.append(
            SpecializationData(
                program_slug=program_slug,
                slug=_slug(name),
                name=name,
                description=description,
                source_url=source_url,
                position=position,
                requirements=requirements,
            )
        )
    return result


def parse_specialization_page(html: str, source_url: str) -> list[SpecializationData]:
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main", id="main-content") or soup.find("main")
    if main is None:
        raise ValueError("Specialization page has no main content")
    content = main.find(class_="o-sdb") or main
    program_slug, specialization_slug = _url_metadata(source_url)
    if specialization_slug is None:
        return _multi_specialization_page(content, program_slug=program_slug, source_url=source_url)

    heading_element = main.find("h1") or soup.find("title")
    if heading_element is None:
        raise ValueError("Specialization page has no title")
    heading = _clean(heading_element.get_text(" ", strip=True))
    name = re.sub(r"\s*[-–]\s*Speciali[sz]ation.*$", "", heading, flags=re.I)
    name = re.sub(r"^Speciali[sz]ation\s*\(\d+\)\s*:\s*", "", name, flags=re.I).strip()
    if not name:
        raise ValueError("Specialization page has an empty title")

    courses: list[SpecializationCourseData] = []
    requirements: list[SpecializationRequirementData] = []
    courses_by_key: dict[str, SpecializationCourseData] = {}
    for table, context in _contextual_tables(content):
        rows = table.find_all("tr")
        provisional_count = sum(1 for row in rows if row.find("a", href=re.compile(r"/course/", re.I)))
        requirement_type, required_ects, required_count, role = _requirement_metadata(context, provisional_count)
        member_keys: list[str] = []
        for row in rows:
            course = _course_from_row(row, role=role, source_url=source_url, position=len(courses))
            if course is None:
                continue
            existing = courses_by_key.get(course.key)
            if existing is None:
                courses_by_key[course.key] = course
                courses.append(course)
            member_keys.append(course.key)
        if member_keys:
            requirements.append(
                SpecializationRequirementData(
                    requirement_type=requirement_type,
                    description=context or "Courses associated with this specialization.",
                    required_ects=required_ects,
                    required_count=required_count,
                    member_keys=list(dict.fromkeys(member_keys)),
                    position=len(requirements),
                )
            )

    terminated = _terminated_courses(content, source_url, len(courses))
    for course in terminated:
        if course.key not in courses_by_key:
            courses_by_key[course.key] = course
            courses.append(course)
    if terminated:
        requirements.append(
            SpecializationRequirementData(
                requirement_type="historical",
                description="Terminated courses that still count towards the specialization.",
                member_keys=[course.key for course in terminated],
                position=len(requirements),
            )
        )

    description = _description(content)
    if not courses and not requirements and description is None:
        raise ValueError("Specialization page contains neither a description nor recognizable course requirements")
    return [
        SpecializationData(
            program_slug=program_slug,
            slug=specialization_slug,
            name=name,
            description=description,
            source_url=source_url,
            position=0,
            courses=courses,
            requirements=requirements,
        )
    ]
