# Skill Compass

Navigating Australia's Data Analytics Job Market Through Skill Intelligence

## Current status

The current implementation provides the reproducible Python environment and
importable package baseline plus Feature 2 JSONL/CSV source mapping and
deterministic cleaning. The consolidated `national_jobs_raw.jsonl` is the
primary national processing input. Feature 3 adds deterministic,
evidence-preserving requirement and skill extraction from typed Feature 2
cleaned records.

Feature 4A adds an explicit, five-item-safe Apify connection test and
conservative result-cap assessment. It does not add national or scheduled
collection.

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

## National processing workflow (no Actor invocation)

After the one-time collection or existing-dataset fetch has created a private
`national_jobs_raw.jsonl`, process that existing local file through Feature 2:

```shell
uv run skill-compass clean-jsonl --input data/private/collections/full/<BACKFILL_ID>/national_jobs_raw.jsonl --mapping sources/apify_seek_current/source_mapping.yaml --output-dir data/processed/national
```

The JSONL adapter reads UTF-8 JSON objects, flattens nested object and array
paths into the versioned source-mapping contract, and then uses the same
canonical mapping, deduplication, cleaning, quality, and output logic as the CSV
adapter. It never starts or reruns an Apify Actor.

Run the implemented Feature 3 extraction stage against the resulting national
cleaned data:

```shell
uv run skill-compass extract-requirements --input data/processed/national/cleaned_jobs.csv --profile profiles/data_analytics/profile.yaml --dictionary profiles/data_analytics/requirements.csv --output-dir data/processed/national/skill_extraction
```

Keep the raw national input and every generated output local and ignored. Role
and seniority classification are later implementation work and are not included
in these commands yet.

## Feature 2: CSV demonstration compatibility

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

CSV remains available for the private 146-row demonstration and sanitised test
fixtures. National processing uses the JSONL command above. PostgreSQL
integration follows in a later controlled work item; it is not implemented
here.

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

## Feature 4A: Apify connection test

Copy `.env.example` to a local `.env` and set `APIFY_TOKEN`. The `.env` file is
ignored and must never be committed. Then run the deliberately bounded test:

```shell
uv run skill-compass test-apify-connection
```

The command resolves `scrapersdelight/seek-jobs-scraper`, requests at most five
test-scope results using the checked-in connection configuration, waits
for completion, and reports only run metadata and counts. It does not print raw
listings or invoke mapping, cleaning, extraction, classification, or analysis.

The warning threshold is 500. A count at or above that threshold reports
`CAP_RISK`, not proven truncation. `CONFIRMED_TRUNCATED` requires explicit,
verified Actor/source metadata showing that more matches existed than were
retrieved.

## Feature 4B: fetch an existing Apify dataset

Retrieve an existing dataset without starting or rerunning its Actor:

```shell
uv run skill-compass fetch-apify --dataset-id DATASET_ID
```

Alternatively, resolve a completed run's default dataset and fetch it:

```shell
uv run skill-compass fetch-apify --run-id RUN_ID
```

The command uses Apify's paginated dataset iterator and writes raw `items.jsonl`
plus `fetch_manifest.json` below `data/private/collections/fetched/`. These
private outputs are ignored by Git. Fetching does not invoke an Actor or run
mapping, cleaning, extraction, classification, or analysis.

Fetch and concatenate every existing dataset referenced by a private national
backfill manifest without invoking an Actor:

```shell
uv run python scripts/fetch_full_backfill.py --manifest data/private/collection_manifests/full_backfill_sources.csv --dry-run
uv run python scripts/fetch_full_backfill.py --manifest data/private/collection_manifests/full_backfill_sources.csv
```

The equivalent installed command is `uv run skill-compass fetch-backfill` with
the same options. Successful scope files are skipped on rerun; `--force`
deliberately re-fetches them. The national JSONL preserves every raw occurrence
in configured scope order. Duplicate detection and survivor selection remain a
Feature 2 responsibility.

To append datasets from every other successful existing run of the configured
`scrapersdelight/seek-jobs-scraper` Actor, use the explicit discovery flag:

```shell
uv run skill-compass fetch-backfill --include-all-successful-runs
```

Discovery uses the SDK's paginated successful-run iterator and never starts or
calls the Actor. This mode does not require or validate the private 66-scope
manifest. Every distinct dataset discovered from a successful Actor run is
written below `supplemental/`, its provenance is recorded in
`supplemental_results.csv`, and every raw occurrence is concatenated into
`national_jobs_raw.jsonl`. The fetch is `COMPLETE` when discovery succeeds and
all discovered datasets are fetched successfully.

Run the live Feature 4 demonstration with:

```shell
uv run python scripts/demo_feature_4.py
```

The demonstration authenticates with `APIFY_TOKEN`, discovers existing
successful runs, retrieves their datasets, reconciles the combined raw JSONL,
and prints dataset, search-scope, cap-risk, and raw-listing summaries. State
counts are derived only from each run's original Actor `INPUT.location` when it
exactly matches a configured SEEK search location. Individual job locations are
not cleaned or normalised, duplicate occurrences remain present, and Feature 2
is not started. Reruns skip successful local datasets unless `--force` is used.

## Feature 4C: one-time full national collection

Review the derived 66-scope national plan without making any Apify request:

```shell
uv run python scripts/run_full_collection.py --dry-run
```

After reviewing the plan, explicitly start the sequential paid backfill with:

```shell
uv run python scripts/run_full_collection.py --execute
```

If an incomplete backfill exists, resume it without rerunning successful scopes:

```shell
uv run python scripts/run_full_collection.py --execute --resume
```

A completed backfill blocks another full execution. `--force` deliberately
creates a new backfill directory and should be used only when another paid
historical collection is intended. Raw scope files, audit manifests, provenance,
and the consolidated national JSONL remain below the ignored
`data/private/collections/full/` directory. Collection never runs through the
processing or demo commands.
