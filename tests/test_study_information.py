import asyncio
from pathlib import Path

import pytest

from importer.study_information import (
    read_snapshot,
    specialization_relative_path,
    study_plan_relative_path,
)
from scripts import get_all_study_information


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://student.dtu.dk/studieordninger/Bachelor/softwareteknologi/studieplan",
            "study_plans/bachelor/softwareteknologi.html",
        ),
        (
            "https://student.dtu.dk/en/programme-specifications/"
            "Bachelor-of-science-in-engineering/General-Engineering/current-study-plan",
            "study_plans/bachelor/general-engineering.html",
        ),
        (
            "https://www.dtu.dk/english/education/graduate/msc-programmes/"
            "computer-science-and-engineering/curriculum",
            "study_plans/master/computer-science-and-engineering.html",
        ),
    ],
)
def test_study_plan_url_has_stable_snapshot_path(url, expected):
    assert study_plan_relative_path(url) == Path(expected)


def test_specialization_url_has_stable_snapshot_path():
    url = (
        "https://www.dtu.dk/english/education/graduate/msc-programmes/"
        "computer-science-and-engineering/specialization/"
        "artificial-intelligence-and-algorithms"
    )

    assert specialization_relative_path(url) == Path(
        "specializations/computer-science-and-engineering/"
        "artificial-intelligence-and-algorithms.html"
    )


def test_specialization_overview_has_stable_snapshot_path():
    url = (
        "https://www.dtu.dk/english/education/graduate/msc-programmes/"
        "technology-entrepreneurship/specialization"
    )

    assert specialization_relative_path(url) == Path(
        "specializations/technology-entrepreneurship/overview.html"
    )


def test_snapshot_paths_reject_non_dtu_hosts():
    with pytest.raises(ValueError, match="dtu.dk"):
        study_plan_relative_path("https://example.com/program/curriculum")


def test_read_snapshot_requires_html(tmp_path):
    relative_path = Path("study_plans/bachelor/example.html")
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_text("not a DTU page", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid HTML"):
        read_snapshot(tmp_path, relative_path)


def test_read_snapshot_returns_saved_html(tmp_path):
    relative_path = Path("study_plans/bachelor/example.html")
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_text("<html><body>Study plan</body></html>", encoding="utf-8")

    assert read_snapshot(tmp_path, relative_path) == "<html><body>Study plan</body></html>"


def test_downloader_saves_program_and_specialization_snapshots(monkeypatch, tmp_path):
    program_url = "https://student.dtu.dk/studieordninger/Bachelor/softwareteknologi/studieplan"
    specialization_url = (
        "https://www.dtu.dk/english/education/graduate/msc-programmes/"
        "computer-science-and-engineering/specialization/cybersecurity"
    )
    pages = {
        program_url: "<html><body>Program</body></html>",
        specialization_url: "<html><body>Specialization</body></html>",
    }

    class FakeClient:
        def __init__(self, request_delay):
            self.request_delay = request_delay

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def fetch(self, url):
            return pages[url]

    monkeypatch.setattr(get_all_study_information, "StudyPlanClient", FakeClient)

    summary, failures = asyncio.run(
        get_all_study_information.download_study_information(
            program_urls=[program_url],
            specialization_urls=[specialization_url],
            output_directory=tmp_path,
            request_delay=0,
        )
    )

    assert summary.downloaded == 2
    assert summary.failed == 0
    assert failures == []
    assert (tmp_path / study_plan_relative_path(program_url)).read_text() == pages[program_url]
    assert (tmp_path / specialization_relative_path(specialization_url)).read_text() == pages[
        specialization_url
    ]
