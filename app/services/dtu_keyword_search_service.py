import re
import threading
from dataclasses import dataclass
from time import monotonic
from xml.etree import ElementTree

import httpx

from app.config import Settings, get_settings


COURSE_NUMBER_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9-]{3,15}$")
ACADEMIC_YEAR_PATTERN = re.compile(r"^(\d{4})-(\d{4})$")
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_CACHE_ENTRIES = 512
SEARCH_PATH = "/coursewebservicev2/course.asmx/SearchDtuShb_Full"


class DtuKeywordSearchError(RuntimeError):
    """Raised when DTU keyword candidates cannot be fetched safely."""


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    course_numbers: tuple[str, ...]


_cache: dict[tuple[str, str, str], _CacheEntry] = {}
_cache_lock = threading.Lock()


def _catalog_version(academic_year: str) -> str:
    match = ACADEMIC_YEAR_PATTERN.fullmatch(academic_year)
    if match is None or int(match.group(2)) != int(match.group(1)) + 1:
        raise DtuKeywordSearchError(
            "academic year must contain consecutive years, e.g. 2026-2027"
        )
    return f"{match.group(1)}/{match.group(2)}"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_keyword_search_response(
    content: bytes,
    *,
    academic_year: str,
    max_candidates: int,
) -> list[str]:
    if len(content) > MAX_RESPONSE_BYTES:
        raise DtuKeywordSearchError("DTU keyword response exceeded the size limit")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise DtuKeywordSearchError("DTU keyword response was not valid XML") from exc

    expected_volume = _catalog_version(academic_year)
    course_numbers: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if _local_name(element.tag) != "CourseList":
            continue
        volume = (element.get("volume") or "").strip()
        if volume and volume != expected_volume:
            continue
        course_number = (element.get("CourseCode") or "").strip().upper()
        if not COURSE_NUMBER_PATTERN.fullmatch(course_number) or course_number in seen:
            continue
        seen.add(course_number)
        course_numbers.append(course_number)
        if len(course_numbers) >= max_candidates:
            break
    return course_numbers


def _request_params(query: str, academic_year: str) -> dict[str, str]:
    return {
        "courseCode": "",
        "searchWords": query,
        "department": "",
        "teachingPeriod": "",
        "CourseCatalogVersion": _catalog_version(academic_year),
        "courseCodeStart": "",
        "teachingLanguage": "",
        "courseIDList": "",
        "resultType": "XMLList",
        "education": "",
        "CourseType": "",
        "MasterRegular": "",
        "openUniversity": "",
        "textStudieboksen": "",
    }


def fetch_dtu_keyword_course_numbers(
    query: str,
    academic_year: str,
    *,
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> list[str]:
    settings = settings or get_settings()
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return []

    url = f"{settings.dtu_base_url.rstrip('/')}{SEARCH_PATH}"
    owns_client = client is None
    if client is None:
        client = httpx.Client(
            timeout=httpx.Timeout(settings.dtu_keyword_search_timeout),
            follow_redirects=True,
            headers={
                "Accept": "application/xml, text/xml",
                "User-Agent": "dtu-course-api/1.0 (+keyword-search)",
            },
        )
    try:
        content = bytearray()
        with client.stream(
            "GET",
            url,
            params=_request_params(normalized_query, academic_year),
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                if len(content) + len(chunk) > MAX_RESPONSE_BYTES:
                    raise DtuKeywordSearchError(
                        "DTU keyword response exceeded the size limit"
                    )
                content.extend(chunk)
        return parse_keyword_search_response(
            bytes(content),
            academic_year=academic_year,
            max_candidates=settings.dtu_keyword_max_candidates,
        )
    except httpx.HTTPError as exc:
        raise DtuKeywordSearchError("DTU keyword request failed") from exc
    finally:
        if owns_client:
            client.close()


def get_dtu_keyword_course_numbers(
    query: str,
    academic_year: str,
) -> list[str]:
    settings = get_settings()
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return []

    cache_key = (
        settings.dtu_base_url.rstrip("/").casefold(),
        academic_year,
        normalized_query.casefold(),
    )
    now = monotonic()
    if settings.dtu_keyword_cache_ttl:
        with _cache_lock:
            cached = _cache.get(cache_key)
            if cached is not None and cached.expires_at > now:
                return list(cached.course_numbers)

    course_numbers = fetch_dtu_keyword_course_numbers(
        normalized_query,
        academic_year,
        settings=settings,
    )
    if settings.dtu_keyword_cache_ttl:
        with _cache_lock:
            for key, entry in list(_cache.items()):
                if entry.expires_at <= now:
                    _cache.pop(key, None)
            while len(_cache) >= MAX_CACHE_ENTRIES:
                _cache.pop(next(iter(_cache)))
            _cache[cache_key] = _CacheEntry(
                expires_at=now + settings.dtu_keyword_cache_ttl,
                course_numbers=tuple(course_numbers),
            )
    return course_numbers


def clear_dtu_keyword_search_cache() -> None:
    with _cache_lock:
        _cache.clear()
