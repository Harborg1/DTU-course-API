import argparse
import re
import sys
import time
from collections.abc import Callable
from xml.etree import ElementTree

import httpx


DEFAULT_BASE_URL = "https://kurser.dtu.dk/coursewebservicev2/course.asmx"
COURSE_NUMBER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,15}$")
CATALOG_VERSION_PATTERN = re.compile(r"^(\d{4})[/-](\d{4})$")


def normalize_catalog_version(value: str) -> str:
    match = CATALOG_VERSION_PATTERN.fullmatch(value.strip())
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValueError("catalog version must have the form YYYY/YYYY or YYYY-YYYY")
    return f"{match.group(1)}/{match.group(2)}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_start_letters(xml: str) -> list[str]:
    root = ElementTree.fromstring(xml)
    prefixes = {
        prefix.strip().upper()
        for element in root.iter()
        if _local_name(element.tag) == "Course"
        and (prefix := element.get("startLetters"))
    }
    if not prefixes:
        raise ValueError("DTU response contained no course-code prefixes")
    return sorted(prefixes)


def parse_course_numbers(xml: str) -> set[str]:
    root = ElementTree.fromstring(xml)
    numbers: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) != "CourseList":
            continue
        value = (element.get("CourseCode") or "").strip().upper()
        if not COURSE_NUMBER_PATTERN.fullmatch(value):
            raise ValueError(f"invalid or missing course number in DTU response: {value!r}")
        numbers.add(value)
    return numbers


def _get_xml(client: httpx.Client, endpoint: str, params: dict[str, str]) -> str:
    response = client.get(endpoint, params=params)
    response.raise_for_status()
    return response.text


def get_all_course_numbers(
    catalog_version: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    request_delay: float = 0.25,
    client: httpx.Client | None = None,
    progress: Callable[[str], None] | None = None,
) -> list[str]:
    if request_delay < 0:
        raise ValueError("request delay cannot be negative")

    catalog_version = normalize_catalog_version(catalog_version)
    base_url = base_url.rstrip("/")
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "Accept": "application/xml, text/xml",
                "User-Agent": "dtu-course-api/1.0 (+course-number discovery)",
            },
        )

    try:
        prefix_xml = _get_xml(
            client,
            f"{base_url}/GetCourseCodeStartLetters",
            {"catalogVersion": catalog_version},
        )
        prefixes = parse_start_letters(prefix_xml)
        numbers: set[str] = set()

        for index, prefix in enumerate(prefixes, start=1):
            if request_delay:
                time.sleep(request_delay)
            course_xml = _get_xml(
                client,
                f"{base_url}/GetCoursesByCourseCodeStartingLetters",
                {"letters": prefix, "catalogversion": catalog_version},
            )
            found = parse_course_numbers(course_xml)
            numbers.update(found)
            if progress is not None:
                progress(f"[{index}/{len(prefixes)}] {prefix}: {len(found)} courses")

        return sorted(numbers)
    finally:
        if owns_client:
            client.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch all published DTU course numbers for a catalog version"
    )
    parser.add_argument(
        "--catalog-version",
        default="2026/2027",
        help="DTU catalog version, e.g. 2026/2027 or 2026-2027",
    )
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.25,
        help="Seconds to wait between requests (default: 0.25)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        numbers = get_all_course_numbers(
            args.catalog_version,
            request_delay=args.request_delay,
            progress=lambda message: print(message, file=sys.stderr),
        )
    except (ValueError, ElementTree.ParseError, httpx.HTTPError) as exc:
        raise SystemExit(f"Could not fetch DTU course numbers: {exc}") from exc

    print("\n".join(numbers))
    print(f"Found {len(numbers)} unique course numbers.", file=sys.stderr)


if __name__ == "__main__":
    main()
