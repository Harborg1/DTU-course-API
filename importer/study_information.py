import re
from pathlib import Path
from urllib.parse import unquote, urlparse


DEFAULT_STUDY_INFORMATION_DIRECTORY = (
    Path(__file__).resolve().parents[1] / "app" / "data" / "study_information"
)


def _url_parts(url: str) -> list[str]:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not (hostname == "dtu.dk" or hostname.endswith(".dtu.dk")):
        raise ValueError(f"Only public HTTPS pages on dtu.dk can be saved: {url}")
    return [unquote(part) for part in parsed.path.split("/") if part]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    if not slug:
        raise ValueError(f"Could not create a snapshot name from {value!r}")
    return slug


def study_plan_relative_path(url: str) -> Path:
    parts = _url_parts(url)
    folded = [part.casefold() for part in parts]

    if "msc-programmes" in folded:
        index = folded.index("msc-programmes")
        try:
            program_slug = _slug(parts[index + 1])
        except IndexError as exc:
            raise ValueError(f"Unsupported DTU study-plan URL: {url}") from exc
        degree = "master"
    elif folded[-1:] in (["studieplan"], ["current-study-plan"]):
        if len(parts) < 2:
            raise ValueError(f"Unsupported DTU study-plan URL: {url}")
        program_slug = _slug(parts[-2])
        degree = "bachelor" if any("bachelor" in part for part in folded) else "other"
    else:
        raise ValueError(f"Unsupported DTU study-plan URL: {url}")

    return Path("study_plans") / degree / f"{program_slug}.html"


def specialization_relative_path(url: str) -> Path:
    parts = _url_parts(url)
    folded = [part.casefold() for part in parts]
    try:
        program_index = folded.index("msc-programmes")
        specialization_index = folded.index("specialization", program_index + 1)
        program_slug = _slug(parts[program_index + 1])
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Unsupported DTU specialization URL: {url}") from exc
    specialization_slug = (
        _slug(parts[specialization_index + 1])
        if specialization_index + 1 < len(parts)
        else "overview"
    )
    return Path("specializations") / program_slug / f"{specialization_slug}.html"


def read_snapshot(snapshot_root: Path, relative_path: Path) -> str:
    path = snapshot_root / relative_path
    html = path.read_text(encoding="utf-8")
    if "<html" not in html.casefold():
        raise ValueError(f"Saved DTU page is not valid HTML: {path}")
    return html
