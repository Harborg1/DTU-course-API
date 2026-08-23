import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree

from app.schemas.course import CourseData


SPACE_RE = re.compile(r"\s+")
COURSE_NUMBER_RE = re.compile(r"(?<![A-Z0-9])([A-Z0-9]{5})(?![A-Z0-9])")
LANGUAGES = {"da-DK": "da", "en-GB": "en"}
LEVELS = {
    "DTU_BSC": ("BSc", "Bachelor"),
    "DTU_DIPLOM": ("BSc", "Diploma Bachelor"),
    "DTU_MSC": ("MSc", "Master"),
    "DTU_PHD": ("PhD", "PhD"),
    "DTU_PARTTIME_DIPLOM": ("Continuing education", "Part-time Diploma"),
    "DTU_PARTTIME_MASTER": ("MSc", "Part-time Master"),
}
LANGUAGE_NAMES = {
    "da-DK": "Danish",
    "en-GB": "English",
}


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    text = SPACE_RE.sub(" ", value.replace("\xad", "").replace("\u200b", "")).strip()
    return text or None


def _elements(root: ElementTree.Element, tag: str) -> list[ElementTree.Element]:
    return [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == tag]


def _first(root: ElementTree.Element, tag: str) -> ElementTree.Element | None:
    return next(iter(_elements(root, tag)), None)


def _attribute(root: ElementTree.Element, tag: str, attribute: str) -> str | None:
    element = _first(root, tag)
    return _clean(element.get(attribute)) if element is not None else None


def _element_text(root: ElementTree.Element, tag: str) -> str | None:
    element = _first(root, tag)
    return _clean(element.text) if element is not None else None


def _localized_attributes(
    root: ElementTree.Element,
    tag: str,
    attribute: str,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for element in _elements(root, tag):
        language = LANGUAGES.get(element.get("Lang", ""))
        value = _clean(element.get(attribute))
        if language and value and language not in values:
            values[language] = value
    return values


def _localized_txt_sections(course: ElementTree.Element, tag: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for text_block in _elements(course, "Txt"):
        language = LANGUAGES.get(text_block.get("Lang", ""))
        if not language:
            continue
        section = next(
            (
                child
                for child in text_block
                if child.tag.rsplit("}", 1)[-1] == tag
            ),
            None,
        )
        value = _clean(section.text) if section is not None else None
        if value:
            values[language] = value
    return values


def _objective_keywords(course: ElementTree.Element) -> dict[str, str]:
    values: dict[str, list[str]] = {"da": [], "en": []}
    for objective in _elements(course, "DTU_ObjectiveKeyword"):
        for text in _elements(objective, "Txt"):
            language = LANGUAGES.get(text.get("Lang", ""))
            value = _clean(text.get("Txt"))
            if language and value:
                values[language].append(value)
    return {language: "\n".join(items) for language, items in values.items() if items}


def _localized_prerequisites(course: ElementTree.Element, tag: str) -> dict[str, str]:
    return _localized_attributes(course, tag, "Txt")


def _recommended_prerequisite_course_numbers(course: ElementTree.Element) -> list[str]:
    numbers: list[str] = []
    seen: set[str] = set()
    for element in _elements(course, "DTU_CoursesTxt"):
        expression = (element.get("Txt") or "").upper()
        for number in COURSE_NUMBER_RE.findall(expression):
            if number not in seen:
                numbers.append(number)
                seen.add(number)
    return numbers


def _parse_last_updated(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})([+-]\d{2}:\d{2})?", value)
    if match:
        suffix = match.group(2) or "+00:00"
        return datetime.fromisoformat(f"{match.group(1)}T00:00:00{suffix}")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _schedule_values(course: ElementTree.Element) -> list[str]:
    class_schedule = _first(course, "Class_Schedule")
    if class_schedule is None:
        return []
    values = {
        value
        for element in _elements(class_schedule, "Schedule")
        if (value := _clean(element.get("ScheduleKey")))
    }
    return sorted(values)


def _period(schedules: list[str]) -> str | None:
    periods = []
    for schedule in schedules:
        match = re.match(r"([EFJ])\d", schedule, re.IGNORECASE)
        if match and (period := match.group(1).upper()) not in periods:
            periods.append(period)
    return ",".join(periods) or None


def _responsible_people(course: ElementTree.Element) -> list[dict]:
    people = []
    for element in _elements(course, "Course_Responsible"):
        description = _first(element, "Description")
        given_name = _element_text(description, "GivenName") if description is not None else None
        family_name = _element_text(description, "FamilyName") if description is not None else None
        email = _element_text(description, "Email") if description is not None else None
        name = _clean(" ".join(part for part in (given_name, family_name) if part))
        people.append(
            {
                "person_key": element.get("PersonKey"),
                "name": name,
                "email": email,
                "primary": element.get("Primary", "false").casefold() == "true",
                "contact": element.get("Contact", "false").casefold() == "true",
                "sort_id": int(element.get("SortID", "0") or 0),
            }
        )
    return sorted(people, key=lambda person: person["sort_id"])


def _examinations(course: ElementTree.Element) -> list[dict]:
    examinations = []
    for element in _elements(course, "Examination"):
        evaluation = _first(element, "Evaluation")
        assessment = _first(element, "Pre_Def_List")
        marking_scale = _first(element, "Marking_Scale")
        aid = _first(element, "Aid")
        duration = _first(element, "DurationKey")
        examinations.append(
            {
                "sort_id": int(element.get("ExaminationSortID", "0") or 0),
                "evaluation_key": evaluation.get("EvaluationKey") if evaluation is not None else None,
                "assessment_key": assessment.get("AssessmentKey") if assessment is not None else None,
                "marking_scale_key": marking_scale.get("Marking_ScaleKey") if marking_scale is not None else None,
                "aid_key": aid.get("AidKey") if aid is not None else None,
                "duration_key": duration.get("Key") if duration is not None else None,
                "assessment_texts": _localized_attributes(element, "Supp_Txt", "Txt"),
                "aid_texts": _localized_attributes(element, "Aid_Txt", "Txt"),
                "date_texts": _localized_attributes(element, "Date_of_Exam_Txt", "Txt"),
            }
        )
    return sorted(examinations, key=lambda exam: exam["sort_id"])


def _no_credit_with(course: ElementTree.Element) -> list[str]:
    values: set[str] = set()
    for element in _elements(course, "No_Credit_Points_With"):
        for value in re.split(r"[/,;\s]+", element.get("CourseCode", "")):
            if value:
                values.add(value.upper())
    return sorted(values)


def parse_course_xml(content: bytes | str) -> CourseData:
    root = ElementTree.fromstring(content)
    course = _first(root, "Course")
    if course is None:
        raise ValueError("XML response did not contain a Course element")

    course_number = _clean(course.get("CourseCode"))
    volume = _clean(course.get("Volume"))
    if not course_number:
        raise ValueError("course code was missing")
    if not volume or not re.fullmatch(r"\d{4}/\d{4}", volume):
        raise ValueError("course volume must have the form YYYY/YYYY")
    academic_year = volume.replace("/", "-")

    titles = _localized_attributes(course, "Title", "Title")
    title = titles.get("en") or titles.get("da")
    if not title:
        raise ValueError(f"course {course_number} did not contain a title")

    point = next(
        (element for element in _elements(course, "Point") if element.get("PointType") == "ECTS"),
        None,
    )
    try:
        ects = Decimal(_clean(point.text)) if point is not None and _clean(point.text) else None
    except InvalidOperation as exc:
        raise ValueError(f"course {course_number} contained invalid ECTS") from exc

    programme_level_code = _attribute(course, "CBS_Programme_Level", "CBS_Programme_LevellKey")
    level, course_type = LEVELS.get(programme_level_code, (None, programme_level_code))
    teaching_language_code = _attribute(course, "Teaching_Language", "LangCode")
    location_code = _attribute(course, "Location", "Key")
    schedules = _schedule_values(course)
    people = _responsible_people(course)
    examinations = _examinations(course)

    contents = _localized_txt_sections(course, "Contents")
    descriptions = _localized_txt_sections(course, "Course_Objectives")
    teaching_methods = _localized_txt_sections(course, "Teaching_And_Learning_Methods")
    literature = _localized_txt_sections(course, "Course_Literature")
    remarks = _localized_txt_sections(course, "Remark")
    prerequisites = _localized_prerequisites(course, "Qualified_Prerequisites_Txt")
    mandatory_prerequisites = _localized_prerequisites(course, "Mandatory_Prerequisites_Txt")
    learning_objectives = _objective_keywords(course)

    main_department = _first(course, "Main_Dep")
    study_board = _first(course, "Study_Board")
    sign_up = _first(course, "Sign_Up")
    registration = _first(sign_up, "Pre_Def_List") if sign_up is not None else None
    primary = next((person for person in people if person["primary"]), people[0] if people else None)
    teacher_names = [person["name"] for person in people if person["name"]]
    first_exam = examinations[0] if examinations else None

    return CourseData(
        course_number=course_number,
        academic_year=academic_year,
        university=(course.get("University") or "dtu").casefold(),
        programme_level_code=programme_level_code,
        teaching_language_code=teaching_language_code,
        location_code=location_code,
        study_board_code=study_board.get("Study_BoardKey") if study_board is not None else None,
        title=title,
        title_da=titles.get("da"),
        title_en=titles.get("en"),
        ects=ects,
        level=level,
        course_type=course_type,
        language=LANGUAGE_NAMES.get(teaching_language_code, teaching_language_code),
        department_code=main_department.get("UID") if main_department is not None else None,
        period=_period(schedules),
        schedule=", ".join(schedules) or None,
        campus=location_code.replace("_", " ") if location_code else None,
        prerequisites=prerequisites.get("en") or prerequisites.get("da"),
        prerequisites_da=prerequisites.get("da"),
        prerequisites_en=prerequisites.get("en"),
        mandatory_prerequisites=mandatory_prerequisites.get("en") or mandatory_prerequisites.get("da"),
        mandatory_prerequisites_da=mandatory_prerequisites.get("da"),
        mandatory_prerequisites_en=mandatory_prerequisites.get("en"),
        exam="; ".join(
            value
            for value in (
                first_exam.get("assessment_key") if first_exam else None,
                first_exam.get("duration_key") if first_exam else None,
                first_exam.get("aid_key") if first_exam else None,
            )
            if value
        ) or None,
        evaluation=first_exam.get("evaluation_key") if first_exam else None,
        description=descriptions.get("en") or descriptions.get("da"),
        description_da=descriptions.get("da"),
        description_en=descriptions.get("en"),
        content=contents.get("en") or contents.get("da"),
        content_da=contents.get("da"),
        content_en=contents.get("en"),
        learning_objectives=learning_objectives.get("en") or learning_objectives.get("da"),
        learning_objectives_da=learning_objectives.get("da"),
        learning_objectives_en=learning_objectives.get("en"),
        teaching_methods=teaching_methods.get("en") or teaching_methods.get("da"),
        teaching_methods_da=teaching_methods.get("da"),
        teaching_methods_en=teaching_methods.get("en"),
        literature=literature.get("en") or literature.get("da"),
        literature_da=literature.get("da"),
        literature_en=literature.get("en"),
        course_responsible=primary.get("name") if primary else None,
        teachers=", ".join(teacher_names) or None,
        registration_requirements=registration.get("PlaceKey") if registration is not None else None,
        remarks=remarks.get("en") or remarks.get("da"),
        remarks_da=remarks.get("da"),
        remarks_en=remarks.get("en"),
        schedules=schedules,
        responsible_people=people,
        examinations=examinations,
        no_credit_with=_no_credit_with(course),
        recommended_prerequisite_course_numbers=(
            _recommended_prerequisite_course_numbers(course)
        ),
        source_url=f"https://kurser.dtu.dk/course/{academic_year}/{course_number}",
        source_last_updated=_parse_last_updated(course.get("LastUpdated")),
    )
