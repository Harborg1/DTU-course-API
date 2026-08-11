import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

COURSE_NUMBER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,15}$")


@dataclass(frozen=True)
class Department:
    code: str
    name: str


def parse_departments(html: str) -> list[Department]:
    soup = BeautifulSoup(html, "lxml")
    select = soup.select_one('select[name="department"]')
    if select is None:
        raise ValueError("DTU department selector was not found")
    departments = []
    for option in select.select("option[value]"):
        code = option.get("value", "").strip()
        name = " ".join(option.get_text(" ", strip=True).split())
        if code:
            departments.append(Department(code=code, name=name))
    if not departments:
        raise ValueError("DTU department selector contained no departments")
    return departments


def parse_course_numbers(html: str) -> set[str]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table.table")
    if table is None:
        raise ValueError("DTU course list table was not found")
    numbers: set[str] = set()
    for row in table.select("tbody tr"):
        first_cell = row.find("td")
        if first_cell is None:
            continue
        candidate = first_cell.get_text(" ", strip=True).upper()
        if COURSE_NUMBER_PATTERN.fullmatch(candidate):
            numbers.add(candidate)
        elif candidate:
            logger.warning("Ignoring invalid course number from DTU list: %s", candidate)
    return numbers

