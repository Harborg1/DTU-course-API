import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decimal(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ".").strip())
    except InvalidOperation:
        return None


@dataclass
class StudyPlanCourseData:
    key: str
    course_number: str | None
    title: str
    ects: Decimal | None
    ects_options: list[float]
    schedule: str | None
    source_url: str | None
    requirement_role: str
    position: int


@dataclass
class StudyPlanRequirementData:
    key: str
    requirement_type: str
    description: str
    required_ects: Decimal | None = None
    required_count: int | None = None
    member_keys: list[str] = field(default_factory=list)
    parent_key: str | None = None
    position: int = 0


@dataclass
class StudyPlanSectionData:
    name: str
    position: int
    descriptions: list[str] = field(default_factory=list)
    courses: list[StudyPlanCourseData] = field(default_factory=list)
    requirements: list[StudyPlanRequirementData] = field(default_factory=list)

    @property
    def description(self) -> str | None:
        unique = list(dict.fromkeys(text for text in self.descriptions if text))
        return "\n".join(unique) or None


@dataclass
class StudyProgramData:
    slug: str
    name: str
    degree_type: str
    aliases: list[str]
    academic_year: str | None
    valid_from_year: int | None
    valid_to_year: int | None
    introduction: str | None
    source_url: str
    sections: list[StudyPlanSectionData]

    def hash_payload(self) -> dict:
        return asdict(self)


_KNOWN_SECTIONS = {
    "det polytekniske grundlag",
    "retningsspecifikke kurser",
    "projekter",
    "valgfrie kurser",
    "forhåndsgodkendte kandidatkurser",
}

_SECTION_ALIASES = {
    "polyteknisk grundlag": "Det polytekniske grundlag",
    "polytekniske grundfag": "Det polytekniske grundlag",
}


def _is_msc_curriculum_url(source_url: str) -> bool:
    parts = [part.casefold() for part in urlparse(source_url).path.split("/") if part]
    return "graduate" in parts and "msc-programmes" in parts and parts[-1:] == ["curriculum"]


def _msc_program_metadata(
    soup: BeautifulSoup,
    main: Tag,
    content: Tag,
    source_url: str,
) -> dict:
    heading_element = main.find("h1") or soup.find("title")
    if heading_element is None:
        raise ValueError("MSc curriculum page has no title")
    heading = _clean(heading_element.get_text(" ", strip=True))
    name = re.sub(r"^Curriculum\s+for\s+", "", heading, flags=re.I).strip()
    parsed_url = urlparse(source_url)
    parts = [part for part in parsed_url.path.split("/") if part]
    try:
        programme_index = next(i for i, part in enumerate(parts) if part.casefold() == "msc-programmes")
        slug = parts[programme_index + 1].casefold()
    except (StopIteration, IndexError):
        slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    academic_match = re.search(r"/course/(\d{4}-\d{4})/", str(content), re.I)
    intro_paragraphs = [
        _clean(paragraph.get_text(" ", strip=True))
        for paragraph in main.find_all("p")
        if paragraph.find_parent(class_="o-sdb") is None
    ]
    return {
        "name": name,
        "slug": slug,
        "aliases": list(dict.fromkeys([name, slug.replace("-", " ")])),
        "academic_year": academic_match.group(1) if academic_match else None,
        "introduction": "\n".join(dict.fromkeys(intro_paragraphs)) or None,
    }


_MSC_COUNT_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def _msc_fold(text: str) -> str:
    folded = text.casefold().replace("–", "-").replace("—", "-")
    folded = folded.replace("programme-specific", "programme specific")
    return _clean(folded)


def _msc_ects_values(text: str) -> list[Decimal]:
    values = re.findall(
        r"(\d+(?:[,.]\d+)?)\s*(?:ects(?:\s*points?)?|credit\s*points?|points?)\b",
        _msc_fold(text),
    )
    return [value for raw in values if (value := _decimal(raw)) is not None]


def _msc_table_rule(text: str) -> tuple[str, Decimal | None, int | None]:
    folded = _msc_fold(text)
    values = _msc_ects_values(text)
    first_ects = values[-1] if values else None

    if "recommended" in folded:
        return "recommended_pool", first_ects, None
    if "qualif" in folded and ("programme specific" in folded or "elective" in folded):
        return "eligible_pool", first_ects, None

    count_match = re.search(
        r"(?:choose|select|take)\s+(?:at least\s+)?(one|two|three|four|five|\d+)\s+courses?",
        folded,
    )
    if count_match:
        raw_count = count_match.group(1)
        count = _MSC_COUNT_WORDS.get(raw_count, int(raw_count) if raw_count.isdigit() else 1)
        kind = "min_count" if "at least" in count_match.group(0) else "one_of" if count == 1 else "exact_count"
        return kind, None, count

    word_count_match = re.search(
        r"(?:choose|select|take)\s+(?:at least\s+)?(one|two|three|four|five)\b",
        folded,
    )
    if word_count_match:
        count = _MSC_COUNT_WORDS[word_count_match.group(1)]
        kind = "min_count" if "at least" in word_count_match.group(0) else "one_of" if count == 1 else "exact_count"
        return kind, None, count

    if re.search(r"(?:choose|select|take)\s+at least\s+(?:one|1)\b", folded):
        return "min_count", None, 1
    if re.search(r"(?:choose|select|take)\s+(?:one|1)\b", folded):
        return "one_of", None, 1

    range_match = re.search(
        r"(?:minimum|min\.?|at least)\s*(\d+(?:[,.]\d+)?).*?"
        r"(?:maximum|max\.?|at most)\s*(\d+(?:[,.]\d+)?)\s*(?:ects|points?)",
        folded,
    )
    if range_match:
        return "ects_range", _decimal(range_match.group(1)), None
    if first_ects is not None and re.search(
        r"\d+(?:[,.]\d+)?\s*(?:ects|points?)(?:\s*points?)?\s*\(at least\)",
        folded,
    ):
        return "min_ects", first_ects, None
    if first_ects is not None and re.search(
        r"(?:at most|maximum|max\.?)\s*(?:\([^)]*\)\s*)?\d",
        folded,
    ):
        return "max_ects", first_ects, None
    if first_ects is not None and re.search(
        r"(?:at least|minimum|min\.?)\s*(?:\([^)]*\)\s*)?\d",
        folded,
    ):
        return "min_ects", first_ects, None

    if first_ects is not None and (
        re.search(r"(?:choose|select|take).*?\d+(?:[,.]\d+)?\s*(?:ects|points?)", folded)
        or re.search(r"\d+(?:[,.]\d+)?\s*(?:ects|points?).*?(?:must be chosen|choose)", folded)
        or "options exist for fulfilling" in folded
        or "must add up to" in folded
    ):
        return "group_ects", first_ects, None

    if "mandatory" in folded or "compulsory" in folded:
        if "choose one" in folded:
            return "one_of", None, 1
        return "all_of", first_ects, None
    if "remaining ects" in folded and "chosen from" in folded:
        return "remainder_pool", None, None
    return "course_group", first_ects, None


def _parse_msc_curriculum_page(
    soup: BeautifulSoup,
    main: Tag,
    content: Tag,
    source_url: str,
) -> StudyProgramData:
    """Parse DTU MSc pages, including pools, alternatives, groups, and semester plans."""
    metadata = _msc_program_metadata(soup, main, content, source_url)
    sections: list[StudyPlanSectionData] = []
    section_by_name: dict[str, StudyPlanSectionData] = {}
    current: StudyPlanSectionData | None = None
    pending_texts: list[str] = []
    active_pool: StudyPlanRequirementData | None = None
    requirement_counter = 0

    def next_key() -> str:
        nonlocal requirement_counter
        requirement_counter += 1
        return f"requirement-{requirement_counter}"

    def get_section(name: str) -> StudyPlanSectionData:
        nonlocal current
        key = name.casefold()
        if key not in section_by_name:
            section_by_name[key] = StudyPlanSectionData(name=name, position=len(sections))
            sections.append(section_by_name[key])
        current = section_by_name[key]
        return current

    def add_requirement(
        section: StudyPlanSectionData,
        requirement_type: str,
        description: str,
        *,
        required_ects: Decimal | None = None,
        required_count: int | None = None,
        member_keys: list[str] | None = None,
        parent_key: str | None = None,
    ) -> StudyPlanRequirementData:
        rule = StudyPlanRequirementData(
            key=next_key(),
            requirement_type=requirement_type,
            description=description,
            required_ects=required_ects,
            required_count=required_count,
            member_keys=member_keys or [],
            parent_key=parent_key,
            position=len(section.requirements),
        )
        section.requirements.append(rule)
        return rule

    def add_courses(
        section: StudyPlanSectionData,
        courses: list[StudyPlanCourseData],
        role: str,
    ) -> dict[str, StudyPlanCourseData]:
        by_key = {course.key: course for course in section.courses}
        role_priority = {"elective": 0, "recommended": 1, "choice": 2, "mandatory": 3}
        for course in courses:
            course.requirement_role = role
            existing = by_key.get(course.key)
            if existing is None:
                course.position = len(section.courses)
                section.courses.append(course)
                by_key[course.key] = course
            elif role_priority.get(role, 0) > role_priority.get(existing.requirement_role, 0):
                existing.requirement_role = role
        return by_key

    def major_section(heading_text: str, *, is_h2: bool) -> str | None:
        folded = _msc_fold(heading_text).strip(" .:;()")
        if folded == "programme provision":
            return "Programme provision"
        if folded == "curriculum":
            return "__curriculum__"
        semester = re.match(r"^(1st|2nd|3rd|4th)\s+semester$", folded)
        if is_h2 and semester:
            return f"{semester.group(1)} semester"
        if folded.startswith(("polytechnical foundation", "polytechnic foundation")):
            return "Polytechnical foundation courses"
        if folded.startswith("programme specific"):
            if metadata["slug"] == "technology-entrepreneurship" and current and "semester" in current.name:
                return None
            return "Programme specific courses"
        if folded.startswith(("elective course", "elective courses", "electives")):
            if metadata["slug"] == "technology-entrepreneurship" and current and "semester" in current.name:
                return None
            return "Elective courses"
        if folded.startswith(("master's thesis", "master thesis")):
            return "Master's thesis"
        return None

    def role_for_rule(requirement_type: str) -> str:
        if requirement_type == "all_of":
            return "mandatory"
        if requirement_type == "recommended_pool":
            return "recommended"
        if current and current.name == "Elective courses":
            return "elective"
        return "choice"

    for element in content.find_all(recursive=False):
        if not isinstance(element, Tag) or element.name == "br":
            continue
        text = _clean(element.get_text(" ", strip=True))

        if element.name == "h2":
            section_name = major_section(text, is_h2=True)
            if section_name == "__curriculum__":
                current = None
            elif section_name:
                current = get_section(section_name)
            pending_texts = []
            active_pool = None
            continue

        if element.name in {"ul", "ol"} and current is not None:
            current.descriptions.append(text)
            if current.name != "Programme provision":
                continue
            for item in element.find_all("li", recursive=False):
                item_text = _clean(item.get_text(" ", strip=True))
                folded = _msc_fold(item_text)
                values = _msc_ects_values(item_text)
                thesis_range = re.search(
                    r"(\d+(?:[,.]\d+)?)\s*[-–]\s*(\d+(?:[,.]\d+)?)\s*(?:ects|points?)",
                    folded,
                )
                if not values and ("total" in folded or "entire study" in folded):
                    trailing_number = re.search(r"(\d+(?:[,.]\d+)?)\s*\.?$", folded)
                    if trailing_number:
                        values = [_decimal(trailing_number.group(1))]
                if not values:
                    continue
                if "thesis" in folded and thesis_range:
                    kind = "ects_range"
                    values = [_decimal(thesis_range.group(1))]
                elif "thesis" in folded and len(values) > 1:
                    kind = "ects_range"
                elif "thesis" in folded:
                    kind = "min_ects" if "at least" in folded else "exact_ects"
                elif "total" in folded or "entire study" in folded:
                    kind = "total_ects"
                elif "at least" in folded or "adding up to" in folded:
                    kind = "min_ects"
                else:
                    kind = "exact_ects"
                add_requirement(current, kind, item_text, required_ects=values[0])
            continue

        if element.name in {"p", "div"}:
            emphasis = element.find(["strong", "em"])
            heading_text = _clean(emphasis.get_text(" ", strip=True)) if emphasis else ""
            section_name = major_section(heading_text, is_h2=False) if heading_text else None
            if section_name:
                current = get_section(section_name)
                current.descriptions.append(text)
                active_pool = None
                remainder = text[len(heading_text) :].strip(" .:;")
                if not remainder:
                    pending_texts = [text]
                    continue
                text = remainder
                emphasis = None
                pending_texts = []
            if current is None or not text:
                continue

            current.descriptions.append(text)
            folded = _msc_fold(text)
            if emphasis:
                pending_texts = [text]
            else:
                pending_texts = [*pending_texts[-3:], text]

            if "groups defined below" in folded or "thematic course groups" in folded:
                kind, ects, count = _msc_table_rule(text)
                active_pool = add_requirement(
                    current,
                    kind,
                    text,
                    required_ects=ects,
                    required_count=count,
                )
                group_count = re.search(r"(?:at least|from)\s+(two|three|four|\d+)\s+groups", folded)
                if group_count:
                    raw_count = group_count.group(1)
                    count_value = _MSC_COUNT_WORDS.get(
                        raw_count,
                        int(raw_count) if raw_count.isdigit() else 2,
                    )
                    add_requirement(
                        current,
                        "min_groups",
                        text,
                        required_count=count_value,
                        parent_key=active_pool.key,
                    )

            if current.name == "Elective courses" or "semester" in current.name:
                if any(phrase in folded for phrase in ("may be an elective", "qualifies as an elective", "any course")):
                    add_requirement(current, "eligibility", text)
                max_match = re.search(
                    r"(?:as much as|as many as|up to|maximum)\s+(\d+(?:[,.]\d+)?)\s*(?:ects|credit points?|points?)",
                    folded,
                )
                if max_match:
                    add_requirement(
                        current,
                        "max_ects",
                        text,
                        required_ects=_decimal(max_match.group(1)),
                    )
            if "extra ects" in folded or "surplus points count" in folded:
                add_requirement(current, "excess_counts", text)
            if "only count in one category" in folded or "cannot be counted twice" in folded:
                add_requirement(current, "no_double_count", text)
            if "can be counted towards" in folded:
                add_requirement(current, "cross_pool_credit", text)
            if "cannot be replaced" in folded or "does not exempt" in folded:
                add_requirement(current, "restriction", text)
            additional_match = re.search(
                r"(?:take|choose)\s+another\s+(\d+(?:[,.]\d+)?)\s*(?:ects|points?)",
                folded,
            )
            if additional_match:
                add_requirement(
                    current,
                    "additional_ects",
                    text,
                    required_ects=_decimal(additional_match.group(1)),
                )
            if current.name == "Master's thesis" and "within the scope" in folded:
                add_requirement(current, "thesis_scope", text)
            if "can claim" in folded and "instead" in folded:
                referenced = list(dict.fromkeys(re.findall(r"\b\d{5}\b", text)))
                add_requirement(current, "alternative_credit", text, member_keys=referenced)
            continue

        if element.name != "table" or current is None:
            continue

        context = _clean(" ".join(pending_texts[-3:]))
        parsed_courses, alternative_groups = _parse_course_table(
            element,
            role="choice",
            start_position=len(current.courses),
        )
        member_keys = list(dict.fromkeys(course.key for course in parsed_courses))

        replacement = any(
            phrase in _msc_fold(context)
            for phrase in ("alternative to", "may replace", "can replace", "instead of")
        )
        referenced = set(re.findall(r"\b\d{5}\b", context))
        replacement_target = next(
            (
                rule
                for rule in current.requirements
                if referenced.intersection(rule.member_keys)
                and rule.requirement_type in {"one_of", "group_ects", "all_of"}
            ),
            None,
        )
        if replacement and replacement_target is not None:
            course_by_key = add_courses(current, parsed_courses, "choice")
            replacement_target.member_keys = list(dict.fromkeys([*replacement_target.member_keys, *member_keys]))
            replacement_target.description = _clean(f"{replacement_target.description} {context}")
            pending_texts = []
            continue

        if active_pool is not None:
            course_by_key = add_courses(current, parsed_courses, "choice")
            active_pool.member_keys = list(dict.fromkeys([*active_pool.member_keys, *member_keys]))
            if context and context != active_pool.description:
                add_requirement(
                    current,
                    "course_group",
                    context,
                    member_keys=member_keys,
                    parent_key=active_pool.key,
                )
            for group in alternative_groups:
                titles = [course_by_key[key].title for key in group]
                add_requirement(
                    current,
                    "conditional_one_of",
                    f"Within this pool, these courses are alternatives: {', '.join(titles)}.",
                    required_count=1,
                    member_keys=group,
                    parent_key=active_pool.key,
                )
            pending_texts = []
            continue

        rule_type, required_ects, required_count = _msc_table_rule(context)
        role = role_for_rule(rule_type)
        course_by_key = add_courses(current, parsed_courses, role)

        if rule_type == "all_of" and alternative_groups:
            alternative_keys = {key for group in alternative_groups for key in group}
            mandatory_keys = [key for key in member_keys if key not in alternative_keys]
            if mandatory_keys:
                add_requirement(
                    current,
                    "all_of",
                    context or "All non-alternative courses in this table are mandatory.",
                    required_ects=required_ects,
                    required_count=len(mandatory_keys),
                    member_keys=mandatory_keys,
                )
            for group in alternative_groups:
                for key in group:
                    course_by_key[key].requirement_role = "choice"
                add_requirement(
                    current,
                    "one_of",
                    context or "Choose one course from this mandatory alternative group.",
                    required_count=1,
                    member_keys=group,
                )
        elif current.name == "Polytechnical foundation courses" and alternative_groups and rule_type == "course_group":
            alternative_keys = {key for group in alternative_groups for key in group}
            mandatory_keys = [key for key in member_keys if key not in alternative_keys]
            if mandatory_keys:
                add_requirement(
                    current,
                    "all_of",
                    context or "Mandatory polytechnical foundation courses.",
                    required_count=len(mandatory_keys),
                    member_keys=mandatory_keys,
                )
            for group in alternative_groups:
                add_requirement(
                    current,
                    "one_of",
                    context or "Choose one polytechnical foundation course from this group.",
                    required_count=1,
                    member_keys=group,
                )
        else:
            parent = add_requirement(
                current,
                rule_type,
                context or "Courses listed in this curriculum group.",
                required_ects=required_ects,
                required_count=required_count,
                member_keys=member_keys,
            )
            if rule_type not in {"one_of", "all_of"}:
                for group in alternative_groups:
                    titles = [course_by_key[key].title for key in group]
                    add_requirement(
                        current,
                        "conditional_one_of",
                        f"Within this pool, these courses are alternatives: {', '.join(titles)}.",
                        required_count=1,
                        member_keys=group,
                        parent_key=parent.key,
                    )
        pending_texts = []

    if not sections:
        raise ValueError("MSc curriculum page contains no recognizable sections")
    return StudyProgramData(
        slug=metadata["slug"],
        name=metadata["name"],
        degree_type="Master",
        aliases=metadata["aliases"],
        academic_year=metadata["academic_year"],
        valid_from_year=None,
        valid_to_year=None,
        introduction=metadata["introduction"],
        source_url=source_url,
        sections=sections,
    )


def _section_heading(element: Tag) -> str | None:
    if element.name == "h2":
        candidate = _clean(element.get_text(" ", strip=True))
        if candidate.casefold() in {"studieplan", "curriculum"}:
            return None
        return candidate or None
    emphasis = element.find(["strong", "em"])
    if emphasis is None:
        return None
    candidate = _clean(emphasis.get_text(" ", strip=True)).rstrip(" :")
    folded = candidate.casefold()
    if folded in _SECTION_ALIASES:
        return _SECTION_ALIASES[folded]
    if folded in _KNOWN_SECTIONS:
        return candidate
    return None


def _course_from_row(row: Tag, *, role: str, position: int) -> StudyPlanCourseData | None:
    cells = row.find_all("td", recursive=False)
    if len(cells) < 2:
        return None
    link = row.find("a", href=re.compile(r"/course/", re.I))
    number_match = (
        re.search(r"\b(?:\d{5}|[A-Z]{2}\d{3})\b", _clean(link.get_text(" ", strip=True)), re.I)
        if link
        else None
    )
    course_number = number_match.group(0).upper() if number_match else None
    title = _clean(cells[1].get_text(" ", strip=True))
    if not title:
        return None

    ects_text = _clean(cells[2].get_text(" ", strip=True)) if len(cells) >= 3 else ""
    ects_values = [_decimal(value) for value in re.findall(r"\d+(?:[.,]\d+)?", ects_text)]
    ects_values = [value for value in ects_values if value is not None]
    ects = ects_values[0] if len(ects_values) == 1 else None
    schedule = _clean(cells[-1].get_text(" ", strip=True)) if len(cells) >= 5 else ""
    key = course_number or f"title:{title.casefold()}"
    return StudyPlanCourseData(
        key=key,
        course_number=course_number,
        title=title,
        ects=ects,
        ects_options=[float(value) for value in ects_values],
        schedule=schedule or None,
        source_url=link.get("href") if link else None,
        requirement_role=role,
        position=position,
    )


def _parse_course_table(table: Tag, *, role: str, start_position: int) -> tuple[list[StudyPlanCourseData], list[list[str]]]:
    events: list[StudyPlanCourseData | str] = []
    position = start_position
    for row in table.find_all("tr", recursive=False):
        classes = set(row.get("class", []))
        if "or-connecter" in classes:
            events.append("or")
            continue
        course = _course_from_row(row, role=role, position=position)
        if course is not None:
            events.append(course)
            position += 1

    courses = [event for event in events if isinstance(event, StudyPlanCourseData)]
    alternative_groups: list[list[str]] = []
    index = 0
    while index < len(events):
        event = events[index]
        if not isinstance(event, StudyPlanCourseData):
            index += 1
            continue
        group = [event.key]
        cursor = index
        while (
            cursor + 2 < len(events)
            and events[cursor + 1] == "or"
            and isinstance(events[cursor + 2], StudyPlanCourseData)
        ):
            group.append(events[cursor + 2].key)
            cursor += 2
        if len(group) > 1:
            alternative_groups.append(group)
        index = cursor + 1
    return courses, alternative_groups


def _role_for_section(section_name: str, pending_type: str | None) -> str:
    folded = section_name.casefold()
    if folded in {"projekter", "projects"}:
        return "project"
    if pending_type == "all_of":
        return "mandatory"
    if pending_type in {"min_ects", "min_count", "one_of", "ects_range", "group_ects", "fill_to_ects"}:
        return "choice"
    if folded in {"det polytekniske grundlag", "polytechnical foundation"}:
        return "mandatory"
    if folded == "forhåndsgodkendte kandidatkurser" or ("pre-approved" in folded and "msc" in folded):
        return "preapproved"
    return "elective"


def _requirement_from_text(
    text: str,
    *,
    key: str,
    position: int,
    active_pool_key: str | None,
) -> tuple[StudyPlanRequirementData | None, bool]:
    folded = text.casefold()
    range_match = re.search(
        r"(\d+(?:[,.]\d+)?)\s*[-–]\s*(\d+(?:[,.]\d+)?)\s*(?:ects(?:[- ]?point)?s?|points?)",
        folded,
    )
    ects_match = re.search(r"(\d+(?:[,.]\d+)?)\s*(?:ects(?:-point)?|point)", folded)

    if range_match:
        applies_to_table = any(
            phrase in folded
            for phrase in ("fra denne pulje", "among the courses below", "among those courses")
        )
        return StudyPlanRequirementData(
            key=key,
            requirement_type="ects_range",
            description=text,
            required_ects=_decimal(range_match.group(1)),
            position=position,
        ), applies_to_table

    mandatory_match = re.search(
        r"følgende(?:\s+(\d+))?\s+kurser\s+(?:er\s+)?obligatoriske",
        folded,
    )
    if mandatory_match:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="all_of",
            description=text,
            required_count=int(mandatory_match.group(1)) if mandatory_match.group(1) else None,
            position=position,
        ), True

    generic_mandatory = (
        "obligatorisk" in folded
        and "kurs" in folded
        and "semi-obligatorisk" not in folded
        and any(
            phrase in folded
            for phrase in (
                "nedenstående",
                "alle kurser i",
                "de obligatoriske retnings",
                "obligatoriske retningsspecifikke kurser",
                "obligatoriske at vælge kurserne nedenfor",
            )
        )
    )
    if generic_mandatory:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="all_of",
            description=text,
            position=position,
        ), True

    mandatory_choice_match = re.search(
        r"mandatory to choose\s+(one|two|three|four|\d+)",
        folded,
    )
    if mandatory_choice_match:
        counts = {"one": 1, "two": 2, "three": 3, "four": 4}
        value = mandatory_choice_match.group(1)
        return StudyPlanRequirementData(
            key=key,
            requirement_type="min_count",
            description=text,
            required_count=counts.get(value, int(value) if value.isdigit() else 1),
            position=position,
        ), True

    if (
        folded.rstrip(".:") in {"mandatory", "mandatory for all"}
        or "all the courses in this course block are mandatory" in folded
        or (
            "pulje" in folded
            and "obligatoriske retningsspecifikke" in folded
            and "semi-obligatoriske" not in folded
        )
    ):
        return StudyPlanRequirementData(
            key=key,
            requirement_type="all_of",
            description=text,
            position=position,
        ), True

    if "vælg mindst ét" in folded or "vælge mindst ét" in folded:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="min_count",
            description=text,
            required_count=1,
            parent_key=active_pool_key,
            position=position,
        ), True

    if ("mindst" in folded or re.search(r"\bmin\.?\s*\d", folded)) and ects_match:
        applies_to_table = any(
            phrase in folded
            for phrase in (
                "blandt følgende",
                "blandt de resterende",
                "fra denne pulje",
                "nedenstående",
                "among the courses",
                "among those courses",
            )
        )
        return StudyPlanRequirementData(
            key=key,
            requirement_type="min_ects",
            description=text,
            required_ects=_decimal(ects_match.group(1)),
            position=position,
        ), applies_to_table

    danish_count_match = re.search(
        r"(?:skal\s+(?:den studerende\s+)?(?:desuden\s+)?vælge|vælges)\s+(\d+)\s+kurser\s+fra\s+følgende\s+liste",
        folded,
    )
    if danish_count_match:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="min_count",
            description=text,
            required_count=int(danish_count_match.group(1)),
            position=position,
        ), True

    danish_group_ects = re.search(
        r"(?:skal(?:\s+den studerende)?(?:\s+desuden)?\s+vælge|skal\s+der\s+bestås|der\s+skal\s+bestås)\s+(\d+(?:[,.]\d+)?)\s*(?:ects(?:-point)?|point)\s+(?:fra|blandt)\s+(?:følgende|nedenstående|denne)",
        folded,
    )
    if danish_group_ects:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="group_ects",
            description=text,
            required_ects=_decimal(danish_group_ects.group(1)),
            position=position,
        ), True

    fill_to_match = re.search(r"op\s+til\s+de\s+(\d+(?:[,.]\d+)?)\s*point\s+fra\s+nedenstående", folded)
    if fill_to_match:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="fill_to_ects",
            description=text,
            required_ects=_decimal(fill_to_match.group(1)),
            position=position,
        ), True

    if ects_match and (
        re.search(r"\bchoose\s+\d+(?:[,.]\d+)?\s*ects\s+(?:among|from)", folded)
        or ("opnået" in folded and "fra kursuspuljen" in folded)
    ):
        return StudyPlanRequirementData(
            key=key,
            requirement_type="min_ects",
            description=text,
            required_ects=_decimal(ects_match.group(1)),
            position=position,
        ), True

    if ("op til" in folded or "up to" in folded or "maximum" in folded) and ects_match:
        return StudyPlanRequirementData(
            key=key,
            requirement_type="max_ects",
            description=text,
            required_ects=_decimal(ects_match.group(1)),
            position=position,
        ), False

    if ects_match and (
        "skal bestå" in folded
        or "skal den studerende vælge" in folded
        or "skal den studerende bestå" in folded
        or "students must choose" in folded
    ):
        return StudyPlanRequirementData(
            key=key,
            requirement_type="exact_ects",
            description=text,
            required_ects=_decimal(ects_match.group(1)),
            position=position,
        ), False
    return None, False


def parse_study_plan_page(html: str, source_url: str) -> StudyProgramData:
    soup = BeautifulSoup(html, "lxml")
    main = soup.select_one("main#main-content") or soup
    content = main.select_one(".o-sdb[data-behavior='sdb']")
    if content is None:
        raise ValueError("Study plan page has no DTU study-plan content block")

    if _is_msc_curriculum_url(source_url):
        return _parse_msc_curriculum_page(soup, main, content, source_url)

    heading = _clean((main.find("h1") or soup.find("title")).get_text(" ", strip=True))
    english_name = re.match(r"^Study plan\s+\d{4}\s*-\s*(.+)$", heading, re.I)
    name = (
        english_name.group(1).strip()
        if english_name
        else re.sub(r"^Studieplan for\s+", "", heading, flags=re.I).split(" (")[0].strip()
    )
    parsed_url = urlparse(source_url)
    parts = [part for part in parsed_url.path.split("/") if part]
    slug = (
        parts[-2].casefold()
        if len(parts) >= 2
        else re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    )
    degree_type = "Bachelor" if any("bachelor" in part.casefold() for part in parts) else "Unknown"

    main_text = _clean(main.get_text(" ", strip=True))
    valid_match = re.search(r"optaget i\s+(\d{4})\s+eller senere", main_text, re.I)
    heading_year = re.search(r"Study plan\s+(\d{4})", heading, re.I)
    valid_from_year = int(valid_match.group(1)) if valid_match else int(heading_year.group(1)) if heading_year else None
    academic_match = re.search(r"/course/(\d{4}-\d{4})/", str(content), re.I)
    academic_year = academic_match.group(1) if academic_match else None
    intro_paragraphs = [
        _clean(paragraph.get_text(" ", strip=True))
        for paragraph in main.find_all("p")
        if paragraph.find_parent(class_="o-sdb") is None
    ]

    aliases = [name, slug.replace("-", " ")]
    previous_name = re.search(r"tidligere\s+([^()]+)", heading, re.I)
    if previous_name:
        aliases.append(_clean(previous_name.group(1)))
    aliases = list(dict.fromkeys(alias for alias in aliases if alias))

    sections: list[StudyPlanSectionData] = []
    section_by_name: dict[str, StudyPlanSectionData] = {}
    current: StudyPlanSectionData | None = None
    pending_requirement: StudyPlanRequirementData | None = None
    active_pool_by_section: dict[str, str] = {}
    requirement_counter = 0

    def get_section(section_name: str) -> StudyPlanSectionData:
        nonlocal current
        key = section_name.casefold()
        if key not in section_by_name:
            section_by_name[key] = StudyPlanSectionData(name=section_name, position=len(sections))
            sections.append(section_by_name[key])
        current = section_by_name[key]
        return current

    for element in content.find_all(recursive=False):
        if not isinstance(element, Tag) or element.name == "br":
            continue
        section_heading = _section_heading(element)
        if section_heading:
            current = get_section(section_heading)
            pending_requirement = None

        if element.name == "h2":
            continue

        if current is None:
            continue

        if element.name in {"ul", "ol"}:
            current.descriptions.append(_clean(element.get_text(" ", strip=True)))
            for item in element.find_all("li", recursive=False):
                text = _clean(item.get_text(" ", strip=True))
                requirement_counter += 1
                requirement, _ = _requirement_from_text(
                    text,
                    key=f"requirement-{requirement_counter}",
                    position=len(current.requirements),
                    active_pool_key=active_pool_by_section.get(current.name.casefold()),
                )
                if requirement and requirement.requirement_type == "max_ects":
                    current.requirements.append(requirement)
            continue

        if element.name in {"p", "div"}:
            text = _clean(element.get_text(" ", strip=True))
            if section_heading and text.casefold().startswith(section_heading.casefold()):
                text = text[len(section_heading) :].strip()
            if not text:
                continue
            current.descriptions.append(text)
            requirement_counter += 1
            requirement, applies_to_next_table = _requirement_from_text(
                text,
                key=f"requirement-{requirement_counter}",
                position=len(current.requirements),
                active_pool_key=active_pool_by_section.get(current.name.casefold()),
            )
            if requirement:
                current.requirements.append(requirement)
                if requirement.requirement_type == "min_ects" and applies_to_next_table:
                    active_pool_by_section[current.name.casefold()] = requirement.key
                pending_requirement = requirement if applies_to_next_table else None

                total_match = re.search(
                    r"(?:den studerende\s+)?skal(?:\s+den studerende)?\s+(?:vælge|bestå)\s+(\d+(?:[,.]\d+)?)\s*(?:ects(?:-point)?|point)",
                    text.casefold(),
                )
                if requirement.requirement_type == "all_of" and total_match:
                    current.requirements.insert(
                        max(len(current.requirements) - 1, 0),
                        StudyPlanRequirementData(
                            key=f"requirement-{requirement_counter}-total",
                            requirement_type="exact_ects",
                            description=text,
                            required_ects=_decimal(total_match.group(1)),
                            position=max(len(current.requirements) - 1, 0),
                        ),
                    )
                    requirement.position = len(current.requirements) - 1

            optional_match = re.search(r"kursus\s+((?:\d{5}|[a-z]{2}\d{3}))\b.*\bvalgfrit", text, re.I)
            if optional_match:
                optional_key = optional_match.group(1).upper()
                for course in current.courses:
                    if course.course_number == optional_key:
                        course.requirement_role = "elective"
                for rule in current.requirements:
                    if rule.requirement_type == "all_of" and optional_key in rule.member_keys:
                        rule.member_keys.remove(optional_key)
                        rule.required_count = len(rule.member_keys)
            continue

        if element.name != "table":
            continue

        role = _role_for_section(
            current.name, pending_requirement.requirement_type if pending_requirement else None
        )
        parsed_courses, alternative_groups = _parse_course_table(
            element, role=role, start_position=len(current.courses)
        )
        course_by_key = {course.key: course for course in current.courses}
        for course in parsed_courses:
            existing = course_by_key.get(course.key)
            if existing is None:
                current.courses.append(course)
                course_by_key[course.key] = course
            elif course.requirement_role == "mandatory":
                existing.requirement_role = "mandatory"
            elif existing.requirement_role == "elective" and course.requirement_role == "choice":
                existing.requirement_role = "choice"

        member_keys = list(dict.fromkeys(course.key for course in parsed_courses))
        if pending_requirement is not None:
            if pending_requirement.requirement_type == "fill_to_ects":
                prior_optional = [
                    course.key for course in current.courses if course.requirement_role == "elective"
                ]
                member_keys = list(dict.fromkeys([*prior_optional, *member_keys]))
            pending_requirement.member_keys = member_keys
            if pending_requirement.requirement_type == "all_of" and pending_requirement.required_count is None:
                pending_requirement.required_count = len(member_keys)
        elif current.name.casefold() in {"det polytekniske grundlag", "polytechnical foundation"}:
            alternatives = {key for group in alternative_groups for key in group}
            mandatory_keys = [key for key in member_keys if key not in alternatives]
            if mandatory_keys:
                requirement_counter += 1
                current.requirements.append(
                    StudyPlanRequirementData(
                        key=f"requirement-{requirement_counter}",
                        requirement_type="all_of",
                        description="Alle ikke-alternative kurser i det polytekniske grundlag er obligatoriske.",
                        required_count=len(mandatory_keys),
                        member_keys=mandatory_keys,
                        position=len(current.requirements),
                    )
                )
            for group in alternative_groups:
                requirement_counter += 1
                for key in group:
                    course_by_key[key].requirement_role = "choice"
                titles = [course_by_key[key].title for key in group]
                current.requirements.append(
                    StudyPlanRequirementData(
                        key=f"requirement-{requirement_counter}",
                        requirement_type="one_of",
                        description=f"Vælg ét af: {', '.join(titles)}.",
                        required_count=1,
                        member_keys=group,
                        position=len(current.requirements),
                    )
                )
        pending_requirement = None

    if not sections:
        raise ValueError("Study plan page contains no recognizable sections")
    return StudyProgramData(
        slug=slug,
        name=name,
        degree_type=degree_type,
        aliases=aliases,
        academic_year=academic_year,
        valid_from_year=valid_from_year,
        valid_to_year=None,
        introduction="\n".join(dict.fromkeys(intro_paragraphs)) or None,
        source_url=source_url,
        sections=sections,
    )
