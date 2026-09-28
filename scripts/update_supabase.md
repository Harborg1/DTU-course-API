# Update Supabase after the DTU course data workflow

The GitHub Actions workflow downloads and compares DTU course data, but it does
not update Supabase. When the workflow detects changes, use this procedure to
import the approved snapshot into the database.

Review and merge the pull request on GitHub

1. Open the pull request created by the bot from the
   `automation/refresh-dtu-course-data` branch.
2. Review the report showing new, removed, and changed courses.
3. Verify that all checks have passed.
4. Click `Merge pull request`, followed by `Confirm merge`.

Continue only after the pull request has been merged into GitHub `main`.

Pull GitHub main into the local repository

Run these commands from the repository root:

```bash
git switch main
git status
git fetch origin
git merge --ff-only origin/main
```

`origin` is the GitHub remote. If `--ff-only` is rejected, investigate the
problem before continuing. Do not use `--force` or reset the branch.

Activate the project's Python environment

```bash
source .venv/bin/activate
```

Upgrade the database schema and import the courses

```bash
alembic upgrade head

python -m importer.course_xml_cli \
  --academic-year 2026-2027 \
  --prune \
  --course-numbers course_numbers.txt
```

```bash
python -m importer.course_embedding_cli \
  --academic-year 2026-2027 \
  --dry-run
```

`--dry-run` does not call the embedding API or modify the database. If
`Embeddings Pending` is greater than 0, run:


```bash
python -m importer.course_embedding_cli \
  --academic-year 2026-2027
```

This command requires `EMBEDDING_API_KEY` in `.env`. The job generates only
missing or stale embeddings and can be run again if it is interrupted.

Run the check again when it finishes:

```bash
python -m importer.course_embedding_cli \
  --academic-year 2026-2027 \
  --dry-run
```

The update is complete when the course import reports `Courses Failed: 0` and
the embedding check reports `Embeddings Pending: 0`.

Download and review study information locally

Study plans and specializations are updated manually and are not part of the
GitHub Actions course-data workflow. Download missing snapshots with:

```bash
python scripts/get_all_study_information.py
```

Existing files are left untouched by default. To fetch every page again and
replace only snapshots whose content changed, run:

```bash
python scripts/get_all_study_information.py --overwrite
```

The raw HTML is stored below `app/data/study_information/`. Review the local
changes before importing them:

```bash
git status --short app/data/study_information
git diff -- app/data/study_information
```

Import saved study plans and then saved specializations

Study plans must be imported first because every specialization is linked to
an existing study program:

```bash
python -m importer.study_plan_cli
python -m importer.specialization_cli
```

Both commands read the URL lists in `app/data/` and parse the corresponding
saved HTML files. They do not download pages during the database import.
