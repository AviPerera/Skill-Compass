# Skill Compass

Navigating Australia's Data Analytics Job Market Through Skill Intelligence

## Current status

The current implementation provides the reproducible Python environment and
importable package baseline plus Feature 2 CSV source mapping and deterministic
cleaning.

## Local development

Install Python 3.12 and [uv](https://docs.astral.sh/uv/). Create the local
environment and install the project with its development dependencies:

```shell
uv sync
```

Run the tests and Ruff checks with:

```shell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Verify the installed package and version with:

```shell
uv run python -c "import skill_compass; print(skill_compass.__version__)"
```

## Feature 2: CSV mapping and cleaning

Keep the private demonstration input locally at
`data/private/adelaide_146_jobs_raw.csv`. Never commit private source data.

Run the reusable CSV boundary command with:

```shell
uv run skill-compass clean-csv --input data/private/adelaide_146_jobs_raw.csv --mapping sources/apify_seek_current/source_mapping.yaml --output-dir data/processed/demo_2
```

Run the temporary Demo 2 presentation with:

```shell
uv run python scripts/demo_2_cleaning.py
```

The generated local output directory contains:

- `mapped_jobs.csv`
- `cleaned_jobs.csv`
- `rejected_jobs.csv`
- `data_quality_summary.csv`

CSV is the current demonstration boundary. PostgreSQL integration follows in a
later controlled work item; it is not implemented here.
