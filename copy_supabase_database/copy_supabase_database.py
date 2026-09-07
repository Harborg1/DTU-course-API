import os
from pathlib import Path

import psycopg
from psycopg import sql


env = {}
for raw in Path(".env").read_text().splitlines():
    raw = raw.strip()
    if raw and not raw.startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        env[key] = value

remote_dsn = (
    env.get("MIGRATION_DATABASE_URL") or env["DATABASE_URL"]
).replace("postgresql+psycopg://", "postgresql://", 1)
local_dsn = (
    f"postgresql://dtu:dtu@{os.environ['LOCAL_DB_IP']}:5432/dtu_courses"
)

with psycopg.connect(remote_dsn) as remote, psycopg.connect(local_dsn) as local:
    remote.execute(
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
    )

    tables = [
        row[0]
        for row in remote.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename <> 'alembic_version'
            ORDER BY tablename
            """
        ).fetchall()
    ]
    local_tables = {
        row[0]
        for row in local.execute(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename <> 'alembic_version'
            """
        ).fetchall()
    }
    if set(tables) != local_tables:
        raise RuntimeError(
            f"Public table mismatch: remote={tables}, "
            f"local={sorted(local_tables)}"
        )

    column_query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND is_generated = 'NEVER'
        ORDER BY ordinal_position
    """
    columns = {}
    for table in tables:
        remote_columns = [
            row[0]
            for row in remote.execute(column_query, (table,)).fetchall()
        ]
        local_columns = [
            row[0]
            for row in local.execute(column_query, (table,)).fetchall()
        ]
        if remote_columns != local_columns:
            raise RuntimeError(f"Copyable-column mismatch for {table}")
        columns[table] = remote_columns

    local.execute(
        sql.SQL("TRUNCATE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(
                sql.Identifier("public", table) for table in tables
            )
        )
    )
    local.execute("SET session_replication_role = replica")

    for table in tables:
        column_list = sql.SQL(", ").join(
            map(sql.Identifier, columns[table])
        )
        copy_out = sql.SQL(
            "COPY {} ({}) TO STDOUT (FORMAT BINARY)"
        ).format(sql.Identifier("public", table), column_list)
        copy_in = sql.SQL(
            "COPY {} ({}) FROM STDIN (FORMAT BINARY)"
        ).format(sql.Identifier("public", table), column_list)

        with remote.cursor().copy(copy_out) as source:
            with local.cursor().copy(copy_in) as destination:
                for chunk in source:
                    destination.write(chunk)

        row_count = local.execute(
            sql.SQL("SELECT count(*) FROM {}").format(
                sql.Identifier("public", table)
            )
        ).fetchone()[0]
        print(f"Copied {table}: {row_count} rows")

    for table in tables:
        if "id" not in columns[table]:
            continue
        sequence = local.execute(
            "SELECT pg_get_serial_sequence(%s, %s)",
            (f"public.{table}", "id"),
        ).fetchone()[0]
        if not sequence:
            continue

        maximum_id = local.execute(
            sql.SQL("SELECT max(id) FROM {}").format(
                sql.Identifier("public", table)
            )
        ).fetchone()[0]
        if maximum_id is None:
            local.execute("SELECT setval(%s, 1, false)", (sequence,))
        else:
            local.execute(
                "SELECT setval(%s, %s, true)",
                (sequence, maximum_id),
            )

    local.execute("SET session_replication_role = origin")
    local.commit()
    remote.rollback()

print(f"Completed full copy of {len(tables)} application tables.")