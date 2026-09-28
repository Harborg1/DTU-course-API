import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from importer.specialization_importer import read_specialization_urls
from importer.study_information import (
    DEFAULT_STUDY_INFORMATION_DIRECTORY,
    specialization_relative_path,
    study_plan_relative_path,
)
from importer.study_plan_importer import StudyPlanClient, read_program_urls


DEFAULT_PROGRAM_URLS = REPOSITORY_ROOT / "app" / "data" / "program_urls.txt"
DEFAULT_SPECIALIZATION_URLS = REPOSITORY_ROOT / "app" / "data" / "specializations_urls.txt"


@dataclass
class StudyInformationDownloadSummary:
    discovered: int = 0
    downloaded: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0


def _valid_saved_html(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        return "<html" in path.read_text(encoding="utf-8").casefold()
    except (OSError, UnicodeError):
        return False


def _write_atomically(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(".html.tmp")
    temporary_path.write_text(html, encoding="utf-8")
    temporary_path.replace(path)


def _documents(
    program_urls: list[str],
    specialization_urls: list[str],
    output_directory: Path,
) -> list[tuple[str, str, Path]]:
    documents = [
        ("study plan", url, output_directory / study_plan_relative_path(url))
        for url in program_urls
    ]
    documents.extend(
        ("specialization", url, output_directory / specialization_relative_path(url))
        for url in specialization_urls
    )
    paths: dict[Path, str] = {}
    for _, url, path in documents:
        previous_url = paths.setdefault(path, url)
        if previous_url != url:
            raise ValueError(f"URLs map to the same snapshot file: {previous_url} and {url}")
    return documents


async def download_study_information(
    *,
    program_urls: list[str],
    specialization_urls: list[str],
    output_directory: Path,
    request_delay: float = 0.5,
    overwrite: bool = False,
) -> tuple[StudyInformationDownloadSummary, list[tuple[str, str]]]:
    documents = _documents(program_urls, specialization_urls, output_directory)
    summary = StudyInformationDownloadSummary(discovered=len(documents))
    failures: list[tuple[str, str]] = []

    async with StudyPlanClient(request_delay=request_delay) as client:
        for index, (kind, url, path) in enumerate(documents, start=1):
            if not overwrite and _valid_saved_html(path):
                summary.skipped += 1
                print(f"[{index}/{len(documents)}] {kind}: skipped {path}", file=sys.stderr)
                continue
            try:
                previous = path.read_text(encoding="utf-8") if path.is_file() else None
                html = await client.fetch(url)
                if previous == html:
                    result = "unchanged"
                else:
                    _write_atomically(path, html)
                    result = "updated" if previous is not None else "downloaded"
                setattr(summary, result, getattr(summary, result) + 1)
                print(f"[{index}/{len(documents)}] {kind}: {result} {path}", file=sys.stderr)
            except Exception as exc:
                summary.failed += 1
                failures.append((url, str(exc)))
                print(f"[{index}/{len(documents)}] {kind}: failed {url}", file=sys.stderr)
    return summary, failures


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download raw DTU study-plan and specialization HTML"
    )
    parser.add_argument("--program-urls", type=Path, default=DEFAULT_PROGRAM_URLS)
    parser.add_argument("--specialization-urls", type=Path, default=DEFAULT_SPECIALIZATION_URLS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_STUDY_INFORMATION_DIRECTORY)
    parser.add_argument(
        "--kind",
        choices=("all", "study-plans", "specializations"),
        default="all",
        help="Choose which page type to download (default: all)",
    )
    parser.add_argument("--request-delay", type=float, default=0.5)
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit each selected page type, useful for a small manual download",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Fetch existing snapshots again and replace them only when content changed",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.request_delay < 0:
        raise SystemExit("--request-delay cannot be negative")
    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")

    program_urls = read_program_urls(str(args.program_urls)) if args.kind != "specializations" else []
    specialization_urls = (
        read_specialization_urls(str(args.specialization_urls)) if args.kind != "study-plans" else []
    )
    if args.limit is not None:
        program_urls = program_urls[: args.limit]
        specialization_urls = specialization_urls[: args.limit]

    try:
        summary, failures = asyncio.run(
            download_study_information(
                program_urls=program_urls,
                specialization_urls=specialization_urls,
                output_directory=args.output_dir,
                request_delay=args.request_delay,
                overwrite=args.overwrite,
            )
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not download DTU study information: {exc}") from exc

    print(
        "Complete: "
        f"{summary.downloaded} downloaded, {summary.updated} updated, "
        f"{summary.unchanged} unchanged, {summary.skipped} skipped, "
        f"{summary.failed} failed.",
        file=sys.stderr,
    )
    if failures:
        for url, message in failures:
            print(f"FAILED {url}: {message}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
