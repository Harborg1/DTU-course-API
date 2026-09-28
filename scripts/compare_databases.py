import argparse
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from dotenv import dotenv_values
from sqlalchemy import Connection, func, inspect, select, text
from sqlalchemy.engine import make_url

from app.database import Base, make_engine
from app.models import Course, CourseTranslation, StudyProgram, StudySpecialization


APPLICATION_TABLES = (
    "courses",
    "course_translations",
    "study_programs",
    "study_plan_sections",
    "study_plan_courses",
    "study_plan_requirements",
    "study_plan_requirement_courses",
    "study_specializations",
    "specialization_courses",
    "specialization_requirements",
    "specialization_requirement_courses",
    "import_runs",
    "import_failures",
)


@dataclass
class DatabaseSnapshot:
    identity: dict[str, str | int | None]
    schema_revisions: list[str]
    table_counts: dict[str, int | None]
    missing_tables: list[str]
    entities: dict[str, dict[str, Any]]


def database_identity(database_url: str) -> dict[str, str | int | None]:
    url = make_url(database_url)
    return {
        "driver": url.drivername,
        "host": url.host,
        "port": url.port,
        "database": url.database,
    }


def read_database_url(variable: str, env_file: Path) -> str:
    value = os.environ.get(variable)
    if value:
        return value
    file_values = dotenv_values(env_file) if env_file.is_file() else {}
    file_value = file_values.get(variable)
    if file_value:
        return str(file_value)
    raise ValueError(
        f"{variable} is not set in the environment or {env_file}. "
        "Database URLs are read from environment variables to keep passwords out of command history."
    )


@contextmanager
def readonly_connection(database_url: str) -> Iterator[Connection]:
    engine = make_engine(database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                if connection.dialect.name == "postgresql":
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def _schema_revisions(connection: Connection, available_tables: set[str]) -> list[str]:
    if "alembic_version" not in available_tables:
        return []
    rows = connection.execute(text("SELECT version_num FROM alembic_version"))
    return sorted(str(row.version_num) for row in rows)


def _table_counts(
    connection: Connection,
    available_tables: set[str],
) -> tuple[dict[str, int | None], list[str]]:
    counts: dict[str, int | None] = {}
    missing: list[str] = []
    for table_name in APPLICATION_TABLES:
        if table_name not in available_tables:
            counts[table_name] = None
            missing.append(table_name)
            continue
        table = Base.metadata.tables[table_name]
        counts[table_name] = int(connection.scalar(select(func.count()).select_from(table)) or 0)
    return counts, missing


def _course_entities(connection: Connection, available_tables: set[str]) -> dict[str, Any]:
    if "courses" not in available_tables:
        return {}
    rows = connection.execute(
        select(Course.course_number, Course.academic_year, Course.content_hash)
    )
    return {
        f"{row.academic_year}/{row.course_number}": row.content_hash
        for row in rows
    }


def _study_program_entities(connection: Connection, available_tables: set[str]) -> dict[str, Any]:
    if "study_programs" not in available_tables:
        return {}
    rows = connection.execute(
        select(StudyProgram.source_url, StudyProgram.content_hash)
    )
    return {row.source_url: row.content_hash for row in rows}


def _specialization_entities(connection: Connection, available_tables: set[str]) -> dict[str, Any]:
    required = {"study_programs", "study_specializations"}
    if not required.issubset(available_tables):
        return {}
    rows = connection.execute(
        select(
            StudyProgram.source_url,
            StudySpecialization.slug,
            StudySpecialization.content_hash,
        ).join(StudySpecialization, StudySpecialization.program_id == StudyProgram.id)
    )
    return {
        f"{row.source_url}#{row.slug}": row.content_hash
        for row in rows
    }


def _embedding_entities(connection: Connection, available_tables: set[str]) -> dict[str, Any]:
    required = {"courses", "course_translations"}
    if not required.issubset(available_tables):
        return {}
    rows = connection.execute(
        select(
            Course.course_number,
            Course.academic_year,
            CourseTranslation.language_code,
            CourseTranslation.embedding_text_hash,
            CourseTranslation.embedding_model,
            CourseTranslation.embedding.is_not(None).label("has_embedding"),
        ).join(CourseTranslation, CourseTranslation.course_id == Course.id)
    )
    return {
        f"{row.academic_year}/{row.course_number}/{row.language_code}": {
            "text_hash": row.embedding_text_hash,
            "model": row.embedding_model,
            "has_embedding": bool(row.has_embedding),
        }
        for row in rows
    }


def capture_snapshot(database_url: str) -> DatabaseSnapshot:
    with readonly_connection(database_url) as connection:
        available_tables = set(inspect(connection).get_table_names())
        table_counts, missing_tables = _table_counts(connection, available_tables)
        return DatabaseSnapshot(
            identity=database_identity(database_url),
            schema_revisions=_schema_revisions(connection, available_tables),
            table_counts=table_counts,
            missing_tables=missing_tables,
            entities={
                "courses": _course_entities(connection, available_tables),
                "study_programs": _study_program_entities(connection, available_tables),
                "specializations": _specialization_entities(connection, available_tables),
                "course_embeddings": _embedding_entities(connection, available_tables),
            },
        )


def _compare_entities(source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_keys = set(source)
    target_keys = set(target)
    shared_keys = source_keys & target_keys
    changed_keys = sorted(key for key in shared_keys if source[key] != target[key])
    return {
        "identical": sum(source[key] == target[key] for key in shared_keys),
        "source_only": sorted(source_keys - target_keys),
        "target_only": sorted(target_keys - source_keys),
        "changed": [
            {"key": key, "source": source[key], "target": target[key]}
            for key in changed_keys
        ],
    }


def compare_snapshots(
    source: DatabaseSnapshot,
    target: DatabaseSnapshot,
    *,
    source_label: str,
    target_label: str,
) -> dict[str, Any]:
    table_counts = {
        table_name: {
            "source": source.table_counts[table_name],
            "target": target.table_counts[table_name],
            "equal": source.table_counts[table_name] == target.table_counts[table_name],
        }
        for table_name in APPLICATION_TABLES
    }
    entities = {
        name: _compare_entities(source.entities[name], target.entities[name])
        for name in source.entities
    }
    has_differences = (
        source.schema_revisions != target.schema_revisions
        or source.missing_tables != target.missing_tables
        or any(not item["equal"] for item in table_counts.values())
        or any(
            comparison["source_only"]
            or comparison["target_only"]
            or comparison["changed"]
            for comparison in entities.values()
        )
    )
    return {
        "source": {
            "label": source_label,
            "identity": source.identity,
            "schema_revisions": source.schema_revisions,
            "missing_tables": source.missing_tables,
        },
        "target": {
            "label": target_label,
            "identity": target.identity,
            "schema_revisions": target.schema_revisions,
            "missing_tables": target.missing_tables,
        },
        "schema_equal": source.schema_revisions == target.schema_revisions,
        "table_counts": table_counts,
        "entities": entities,
        "has_differences": has_differences,
    }


def _format_identity(identity: dict[str, Any]) -> str:
    host = identity.get("host") or "local"
    port = f":{identity['port']}" if identity.get("port") else ""
    database = identity.get("database") or ""
    return f"{identity.get('driver')}://{host}{port}/{database}"


def print_report(report: dict[str, Any], *, max_items: int = 20) -> None:
    source = report["source"]
    target = report["target"]
    print(f"Source: {source['label']} ({_format_identity(source['identity'])})")
    print(f"Target: {target['label']} ({_format_identity(target['identity'])})")
    print(
        "Schema revisions: "
        f"{source['schema_revisions'] or ['missing']} -> "
        f"{target['schema_revisions'] or ['missing']}"
    )

    print("\nTable counts")
    print(f"{'Table':42} {'Source':>10} {'Target':>10}  Status")
    for table_name, comparison in report["table_counts"].items():
        source_count = "missing" if comparison["source"] is None else str(comparison["source"])
        target_count = "missing" if comparison["target"] is None else str(comparison["target"])
        status = "same" if comparison["equal"] else "different"
        print(f"{table_name:42} {source_count:>10} {target_count:>10}  {status}")

    print("\nContent hashes and embedding status")
    for name, comparison in report["entities"].items():
        print(
            f"{name}: {comparison['identical']} identical, "
            f"{len(comparison['source_only'])} source-only, "
            f"{len(comparison['target_only'])} target-only, "
            f"{len(comparison['changed'])} changed"
        )
        details = (
            [("source-only", key) for key in comparison["source_only"]]
            + [("target-only", key) for key in comparison["target_only"]]
            + [("changed", item["key"]) for item in comparison["changed"]]
        )
        for status, key in details[:max_items]:
            print(f"  - {status}: {key}")
        if len(details) > max_items:
            print(f"  - ... {len(details) - max_items} more; use --json-output for all details")

    print("\nResult: " + ("differences found" if report["has_differences"] else "databases match"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two DTU Course API databases without modifying either database"
    )
    parser.add_argument(
        "--source-env",
        default="DATABASE_URL",
        help="Environment variable containing the source database URL (default: DATABASE_URL)",
    )
    parser.add_argument(
        "--target-env",
        default="LOCAL_DATABASE_URL",
        help="Environment variable containing the target database URL (default: LOCAL_DATABASE_URL)",
    )
    parser.add_argument("--source-label", default="supabase")
    parser.add_argument("--target-label", default="local")
    parser.add_argument("--env-file", type=Path, default=REPOSITORY_ROOT / ".env")
    parser.add_argument("--json-output", type=Path, help="Write the complete comparison as JSON")
    parser.add_argument(
        "--max-items",
        type=int,
        default=20,
        help="Maximum differing keys printed per data type (default: 20)",
    )
    parser.add_argument(
        "--fail-on-difference",
        action="store_true",
        help="Return exit code 1 when differences are found",
    )
    return parser
    


def main() -> None:
    args = build_parser().parse_args()
    if args.max_items < 0:
        raise SystemExit("--max-items cannot be negative")
    try:
        source_url = read_database_url(args.source_env, args.env_file)
        target_url = read_database_url(args.target_env, args.env_file)
        if source_url == target_url:
            raise ValueError("source and target database URLs are identical")
        source = capture_snapshot(source_url)
        target = capture_snapshot(target_url)
    except Exception as exc:
        raise SystemExit(f"Could not compare databases: {exc}") from exc

    report = compare_snapshots(
        source,
        target,
        source_label=args.source_label,
        target_label=args.target_label,
    )
    print_report(report, max_items=args.max_items)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"\nJSON report: {args.json_output}")
    if args.fail_on_difference and report["has_differences"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
