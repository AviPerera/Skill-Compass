# Skill Compass

Navigating Australia's Data Analytics Job Market Through Skill Intelligence

## Current status

The current implementation provides the reproducible Python environment and
importable package baseline plus Feature 2 CSV source mapping and deterministic
cleaning. Feature 3 adds deterministic, evidence-preserving requirement and
skill extraction from typed Feature 2 cleaned records.

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

## Feature 3: requirement and skill extraction

The versioned Data Analytics requirement dictionary is at
`profiles/data_analytics/requirements.csv`. Matching is deterministic,
section-aware and boundary-controlled, and every accepted occurrence retains a
short reviewable evidence snippet.

Run the reusable extraction boundary with:

```shell
uv run skill-compass extract-requirements --input data/processed/demo_2/cleaned_jobs.csv --profile profiles/data_analytics/profile.yaml --dictionary profiles/data_analytics/requirements.csv --output-dir data/processed/demo_2/skill_extraction
```

Run the temporary live demonstration with:

```shell
uv run python scripts/demo_2_skill_extraction.py
```

The generated extraction directory contains:

- `job_requirement_matches.csv`
- `requirement_evidence.csv`
- `job_extraction_summary.csv`
- `skill_demand_summary.csv`
- `extraction_quality_summary.csv`
- `charts/top_15_skills_by_job_count.png`
- `charts/skills_per_job_distribution.png`

PostgreSQL persistence follows in a later controlled feature. Keep private
inputs and all generated outputs local and ignored; do not commit them.
