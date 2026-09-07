# DTU course data workflow

GitHub only discovers workflow YAML files under `.github/workflows/`. The active
workflow is therefore `.github/workflows/check-course-data.yml`; the reusable
comparison helper lives in this directory.

The workflow runs every Monday at 04:17 UTC and can also be started manually
from the Actions tab. Scheduled runs use the repository variable
`DTU_CATALOG_VERSION`, falling back to `2026/2027` when the variable is absent.

It downloads all published course numbers and XML files into a temporary
directory, validates and compares them with `course_numbers.txt` and
`app/data/course_information/`, runs the offline tests, and creates or updates
the branch `automation/refresh-dtu-course-data` and a pull request when data has
changed.

The workflow does not receive database credentials and never connects to
Supabase. Importing an approved snapshot and regenerating embeddings remain
separate, explicitly controlled operations.

For automatic pull-request creation, enable **Allow GitHub Actions to create and
approve pull requests** under repository Settings > Actions > General.
