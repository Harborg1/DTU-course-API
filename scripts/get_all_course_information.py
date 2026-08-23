import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from xml.etree import ElementTree

import httpx


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPOSITORY_ROOT / "course_numbers.txt"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "app" / "data" / "course_information"
DEFAULT_BASE_URL = "https://kurser.dtu.dk/coursewebservicev2/course.asmx"
COURSE_NUMBER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,15}$")
YEAR_GROUP_PATTERN = re.compile(r"^(\d{4})[/-](\d{4})$")
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class CourseResponseError(ValueError):
    pass


@dataclass
class DownloadSummary:
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0


class RequestRateLimiter:
    def __init__(self, interval: float):
        self.interval = interval
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            remaining = self.interval - (monotonic() - self._last_request)
            if remaining > 0:
                await asyncio.sleep(remaining)
            self._last_request = monotonic()


def normalize_year_group(value: str) -> str:
    match = YEAR_GROUP_PATTERN.fullmatch(value.strip())
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise ValueError("year group must have the form YYYY/YYYY or YYYY-YYYY")
    return f"{match.group(1)}/{match.group(2)}"


def read_course_numbers(path: Path) -> list[str]:
    numbers: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        value = line.strip().upper()
        if not value:
            continue
        if not COURSE_NUMBER_PATTERN.fullmatch(value):
            raise ValueError(f"invalid course number on line {line_number}: {value!r}")
        numbers.add(value)
    if not numbers:
        raise ValueError(f"no course numbers found in {path}")
    return sorted(numbers)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def validate_course_xml(content: bytes, course_number: str, year_group: str) -> None:
    root = ElementTree.fromstring(content)
    courses = [element for element in root.iter() if _local_name(element.tag) == "Course"]
    matching_course = next(
        (
            element
            for element in courses
            if (element.get("CourseCode") or "").strip().upper() == course_number
        ),
        None,
    )
    if matching_course is None:
        raise CourseResponseError(f"response did not contain course {course_number}")
    response_year = (matching_course.get("Volume") or "").strip()
    if response_year != year_group:
        raise CourseResponseError(
            f"course {course_number} returned year group {response_year!r}, expected {year_group!r}"
        )


def _existing_file_is_valid(path: Path, course_number: str, year_group: str) -> bool:
    if not path.is_file():
        return False
    try:
        validate_course_xml(path.read_bytes(), course_number, year_group)
    except (OSError, ElementTree.ParseError, CourseResponseError):
        return False
    return True


def _write_atomically(path: Path, content: bytes) -> None:
    temporary_path = path.with_suffix(".txt.tmp")
    temporary_path.write_bytes(content)
    temporary_path.replace(path)


async def _fetch_course(
    client: httpx.AsyncClient,
    limiter: RequestRateLimiter,
    *,
    base_url: str,
    course_number: str,
    year_group: str,
    attempts: int,
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            await limiter.wait()
            response = await client.get(
                f"{base_url}/GetCourse",
                params={"courseCode": course_number, "yearGroup": year_group},
            )
            if response.status_code in RETRYABLE_STATUS_CODES:
                raise httpx.HTTPStatusError(
                    f"retryable response {response.status_code}",
                    request=response.request,
                    response=response,
                )
            response.raise_for_status()
            validate_course_xml(response.content, course_number, year_group)
            return response.content
        except (httpx.HTTPError, ElementTree.ParseError, CourseResponseError) as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
    assert last_error is not None
    raise last_error


async def download_course_information(
    course_numbers: list[str],
    *,
    year_group: str,
    output_directory: Path,
    base_url: str = DEFAULT_BASE_URL,
    concurrency: int = 3,
    request_delay: float = 0.25,
    attempts: int = 4,
    overwrite: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[DownloadSummary, list[tuple[str, str]]]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    if request_delay < 0:
        raise ValueError("request delay cannot be negative")
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    year_group = normalize_year_group(year_group)
    output_directory.mkdir(parents=True, exist_ok=True)
    limiter = RequestRateLimiter(request_delay)
    semaphore = asyncio.Semaphore(concurrency)
    summary = DownloadSummary()
    failures: list[tuple[str, str]] = []
    completed = 0
    counter_lock = asyncio.Lock()

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        transport=transport,
        headers={
            "Accept": "application/xml, text/xml",
            "User-Agent": "dtu-course-api/1.0 (+course-information importer)",
        },
    ) as client:

        async def download_one(course_number: str) -> None:
            nonlocal completed
            destination = output_directory / f"{course_number}.txt"
            if not overwrite and _existing_file_is_valid(
                destination, course_number, year_group
            ):
                result = "skipped"
                error_message = None
            else:
                try:
                    async with semaphore:
                        content = await _fetch_course(
                            client,
                            limiter,
                            base_url=base_url.rstrip("/"),
                            course_number=course_number,
                            year_group=year_group,
                            attempts=attempts,
                        )
                    _write_atomically(destination, content)
                    result = "downloaded"
                    error_message = None
                except (httpx.HTTPError, ElementTree.ParseError, CourseResponseError) as exc:
                    result = "failed"
                    error_message = str(exc)

            async with counter_lock:
                completed += 1
                setattr(summary, result, getattr(summary, result) + 1)
                if error_message is not None:
                    failures.append((course_number, error_message))
                print(
                    f"[{completed}/{len(course_numbers)}] {course_number}: {result}",
                    file=sys.stderr,
                )

        await asyncio.gather(*(download_one(number) for number in course_numbers))

    return summary, sorted(failures)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download GetCourse XML for every DTU course number"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--year-group", default="2026/2027")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--request-delay", type=float, default=0.25)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        course_numbers = read_course_numbers(args.input)
        if args.limit is not None:
            if args.limit < 1:
                raise ValueError("limit must be at least 1")
            course_numbers = course_numbers[: args.limit]
        summary, failures = asyncio.run(
            download_course_information(
                course_numbers,
                year_group=args.year_group,
                output_directory=args.output_dir,
                concurrency=args.concurrency,
                request_delay=args.request_delay,
                attempts=args.attempts,
                overwrite=args.overwrite,
            )
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not download DTU course information: {exc}") from exc

    print(
        f"Complete: {summary.downloaded} downloaded, "
        f"{summary.skipped} skipped, {summary.failed} failed.",
        file=sys.stderr,
    )
    if failures:
        for course_number, message in failures:
            print(f"FAILED {course_number}: {message}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
