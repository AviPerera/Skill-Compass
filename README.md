# Skill Compass

**Navigating Australia’s Data Analytics Job Market Through Skill Intelligence**

Skill Compass is a university capstone project that turns Australian job-advertisement data into structured, explainable insights about skills, roles, seniority, locations, work arrangements and employment types.

## Phase 2 status: complete

Phase 2 is complete. The final repository contains a reusable Python processing package, the governed national analysis outputs, a Power BI-compatible presentation export, and a React dashboard that presents the final results.

Final national run — data as of **13 August 2026**:

| Stage | Result |
| --- | ---: |
| Raw occurrences collected | 3,088 |
| Unique canonical jobs | 3,028 |
| Cross-scope overlaps removed | 60 |
| Jobs included in the final governed analysis | 748 |
| Jobs excluded | 1,243 |
| Jobs retained for review | 1,037 |
| Power BI presentation views | 26 |

> **Important:** the 748 jobs are the final governed analytical population. The 3,028 jobs are the unique canonical records used for pipeline reconciliation.

---

## What is included

Phase 2 is implemented as nine main repository features:

| Feature | Capability | What it does |
| --- | --- | --- |
| **1** | Environment baseline | Provides a reproducible Python 3.12 project with locked dependencies, tests and Ruff checks. |
| **2** | Mapping and cleaning | Converts raw source fields into a stable canonical schema, cleans records and reconciles duplicates/rejections. |
| **3** | Requirement extraction | Extracts governed skills and job requirements from title, summary, bullet points and descriptions while retaining evidence. |
| **4** | National collection | Supports Apify connection testing, existing-dataset retrieval and the controlled 66-scope national collection. |
| **5** | Role classification | Classifies jobs into governed role groups while retaining `Other` and `Review` when evidence is insufficient. |
| **6** | Seniority classification | Classifies Entry-level, Junior, Mid-level and Senior roles while preserving `Unknown` and `Review` outcomes. |
| **7** | Profile relevance | Separates jobs into `Included`, `Excluded` and `Review` so dashboard insights use a defensible denominator. |
| **8** | Analytics outputs | Produces skill demand, role-specific demand, geography, employment, work-mode and skill-combination analytics. |
| **9** | Power BI export | Builds the governed 26-view presentation contract as JSON and Excel for Power BI and downstream presentation use. |

The central design principle is **configuration over code**. Source-specific fields and Data Analytics-specific rules are kept outside the reusable Python engine.

---

# Quick start

There are two ways to use the repository:

1. **Run the dashboard only** — fastest option; no Python processing is required.
2. **Run the Python package** — reproduce the processing workflow from source data and regenerate the analytical outputs.

---

# Option 1 — Run the dashboard only

The React dashboard can run independently from the Python package. The repository already contains the prepared dashboard data required by the frontend.

## Requirements

- Node.js **20 or newer**
- pnpm **10 or newer** (recommended because the repository includes `pnpm-lock.yaml`)
- npm, which is included with Node.js, may be used as an alternative

## Start the dashboard

From the repository root:

```powershell
cd skill-compass-front-end
pnpm install
pnpm dev
```

Open the address printed by Vite, normally:

```text
http://localhost:5173
```

The dashboard contains six pages:

- Executive Summary
- Skills Analysis
- Role Analysis
- Location Insights
- Graduate Roadmap
- Methodology

## Frontend data flow

```text
Skill Compass Python outputs
        ↓
skill-compass-front-end/data/dashboard-data.json
        ↓
React filtering and aggregation
        ↓
Six-page dashboard
```

The dashboard can therefore be opened and explored **without rerunning the Python pipeline**.

## Useful frontend commands

| Command | Purpose |
| --- | --- |
| `pnpm dev` | Start the local development server |
| `pnpm typecheck` | Check the TypeScript source |
| `pnpm build` | Type-check and create the production build |
| `pnpm preview` | Preview the production build locally |
| `pnpm data:build` | Regenerate `dashboard-data.json` from the latest Feature 9 export |

If you prefer npm:

```powershell
npm install
npm run dev
```

---

# Option 2 — Run the Python package

Use this option if you want to reproduce the analysis, process another dataset, or adapt Skill Compass to another job-market field.

## Requirements

- Python **3.12**
- [uv](https://docs.astral.sh/uv/)
- An Apify token only if you want to collect/fetch live source data

## 1. Install the project

From the repository root:

```powershell
uv sync
```

Verify the package:

```powershell
uv run python -c "import skill_compass; print(skill_compass.__version__)"
```

Run the quality checks:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

---

## 2. Configure Apify only if collecting data

Copy the environment template:

```powershell
Copy-Item .env.example .env
```

Add your token to `.env`:

```text
APIFY_TOKEN=your_token_here
```

Never commit `.env` or your API token.

Test the connection with the bounded five-item connection test:

```powershell
uv run skill-compass test-apify-connection
```

---

## 3. Run a new national collection

First inspect the planned collection without making a paid request:

```powershell
uv run python scripts/run_full_collection.py --dry-run
```

When the plan is correct, start the one-time collection:

```powershell
uv run python scripts/run_full_collection.py --execute
```

If a previous backfill stopped before completion:

```powershell
uv run python scripts/run_full_collection.py --execute --resume
```

> **Cost warning:** the full collection invokes the configured Apify Actor and can consume paid Apify usage. Always use `--dry-run` first.

The completed backfill creates a consolidated file similar to:

```text
data/private/collections/full/<BACKFILL_ID>/national_jobs_raw.jsonl
```

Private collection data should remain local and ignored by Git.

---

## 4. Map and clean the national data — Feature 2

```powershell
uv run skill-compass clean-jsonl `
  --input data/private/collections/full/<BACKFILL_ID>/national_jobs_raw.jsonl `
  --mapping sources/apify_seek_current/source_mapping.yaml `
  --output-dir data/processed/national
```

Main outputs:

```text
data/processed/national/
├── mapped_jobs.csv
├── cleaned_jobs.csv
├── rejected_jobs.csv
└── data_quality_summary.csv
```

The final national run reconciled:

```text
3,028 input records = 3,028 cleaned + 0 rejected
```

---

## 5. Extract skills and requirements — Feature 3

```powershell
uv run skill-compass extract-requirements `
  --input data/processed/national/cleaned_jobs.csv `
  --profile profiles/data_analytics/profile.yaml `
  --dictionary profiles/data_analytics/requirements.csv `
  --output-dir data/processed/national/skill_extraction
```

This stage uses the governed requirement dictionary and retains reviewable evidence for matched requirements.

---

## 6. Classify roles — Feature 5

```powershell
uv run skill-compass classify-roles `
  --input data/processed/national/cleaned_jobs.csv `
  --rules profiles/data_analytics/role_rules.yaml `
  --output-dir data/processed/national/role_classification
```

---

## 7. Classify seniority — Feature 6

```powershell
uv run skill-compass classify-seniority `
  --input data/processed/national/cleaned_jobs.csv `
  --rules profiles/data_analytics/seniority_rules.yaml `
  --output-dir data/processed/national/seniority_classification
```

---

## 8. Run profile relevance — Feature 7

Feature 7 classifies every canonical job as `Included`, `Excluded` or `Review` using the governed relevance rules and the existing Feature 2, 3, 5 and 6 outputs. Run it manually with:

```powershell
uv run skill-compass classify-relevance `
  --input data/processed/national `
  --profile data_analytics `
  --rules profiles/data_analytics/relevance_rules.yaml `
  --output-dir data/processed/national/profile_relevance
```

Main outputs:

```text
data/processed/national/profile_relevance/
├── job_profile_relevance.csv
├── profile_relevance_evidence.csv
├── profile_relevance_summary.csv
├── profile_relevance_review_queue.csv
└── profile_relevance_diagnostics.csv
```

Feature 8 uses only records whose Feature 7 `relevance_status` is `included`. `Excluded` and relevance-`Review` records remain in the governed outputs for reconciliation and manual validation but do not enter the 748-job analytical denominator.

`Unknown` is not a Feature 7 relevance status. It is a governed role/seniority classification outcome from Features 5 and 6. An otherwise relevance-`Included` job may retain an `Unknown` or `Review` role/seniority outcome in the backend governance outputs; the frontend keeps the job in overall totals but hides those values from categorical filters and charts.

---

## 9. Build the final analytics — Feature 8

```powershell
uv run skill-compass build-analytics `
  --input data/processed/national `
  --output-dir data/processed/national/analytics
```

Feature 8 combines the cleaned, extraction, role, seniority and relevance outputs into channel-neutral analytical results.

---

## 10. Build the Power BI presentation export — Feature 9

```powershell
uv run skill-compass export-powerbi `
  --input data/processed/national `
  --output-dir data/processed/national/powerbi
```

Main outputs:

```text
data/processed/national/powerbi/
├── skill_compass_powerbi_live.json
└── skill_compass_powerbi_live.xlsx
```

The export reproduces the governed Power BI contract, including the expected table names, columns and semantic structure.

After generating a new Feature 9 export, refresh the frontend dataset with:

```powershell
cd skill-compass-front-end
pnpm data:build
```

Then start the dashboard again:

```powershell
pnpm dev
```

---

# Adapt Skill Compass to another job field

You should **not need to rewrite the core Python package** for a compatible occupation/domain.

For example, to adapt the project from Data Analytics to Accounting, Cybersecurity or another field, copy the existing profile folder and edit the configuration files below.

## Configuration files to change

| File | Change this when... |
| --- | --- |
| `profiles/data_analytics/profile.yaml` | Changing the occupation profile, profile metadata, active categories or inclusion settings. |
| `profiles/data_analytics/requirements.csv` | Changing the skills, tools, qualifications, aliases and requirement categories to extract. |
| `profiles/data_analytics/role_rules.yaml` | Changing the role groups and the evidence/rules used to classify them. |
| `profiles/data_analytics/seniority_rules.yaml` | Changing seniority labels, title markers, experience rules or review logic. |
| `profiles/data_analytics/pathway_rules.yaml` | **Planned for the next phase.** It will govern career pathways, roadmap priorities and pathway-specific difficulty or sequencing rules when implemented. This file is not present in the current repository. |
| `sources/apify_seek_current/source_mapping.yaml` | **Only** when the source/Actor or source field names change. |

Recommended approach:

```text
profiles/
├── data_analytics/
│   ├── profile.yaml
│   ├── requirements.csv
│   ├── role_rules.yaml
│   └── seniority_rules.yaml
└── your_new_profile/
    ├── profile.yaml
    ├── requirements.csv
    ├── role_rules.yaml
    └── seniority_rules.yaml
```

Governed pathway priority, difficulty and learning-stage configuration will be implemented in the next phase. Until then, do not create placeholder `pathway_rules.yaml` files or infer roadmap recommendations from job advertisements alone.

### If the source stays the same

If you continue using the same SEEK/Apify source structure, keep:

```text
sources/apify_seek_current/source_mapping.yaml
```

unchanged.

### If the source changes

Create or update a source mapping so the new source fields are translated into the same canonical fields:

```text
sources/<your_source>/source_mapping.yaml
```

The central cleaning, extraction, classification and analytics modules should remain unchanged for compatible sources and domains.

---

# Repository structure

```text
skill-compass/
├── skill-compass-front-end/         # React + Vite dashboard
│   ├── data/
│   │   └── dashboard-data.json
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
│
├── profiles/
│   └── data_analytics/             # Domain configuration
│
├── sources/
│   └── apify_seek_current/         # Source field mapping
│
├── src/
│   └── skill_compass/              # Reusable Python package
│       ├── collection/
│       ├── mapping/
│       ├── cleaning/
│       ├── extraction/
│       ├── classification/
│       ├── analytics/
│       └── exports/
│
├── scripts/                        # Collection and demonstration runners
├── tests/                          # Unit, integration and data-quality tests
├── data/
│   ├── private/                    # Private/raw source data — ignored
│   └── processed/                  # Generated processing outputs
├── powerbi/                        # Power BI reference workbook
├── docs/                           # Architecture, methodology and project documentation
├── pyproject.toml
├── uv.lock
└── README.md
```

---

# Data and privacy notes

- Do not commit `.env`, API tokens or private source datasets.
- Raw job descriptions, contact information and tracking fields should not be exposed through the dashboard data contract.
- Skill Compass analyses **advertised job-market demand**. It does not represent every Australian vacancy or the hidden job market.
- Backend governance outputs retain `Unknown`, `Other` and `Review` outcomes when evidence is insufficient instead of forcing a classification. The frontend retains relevance-included jobs in overall totals but hides `Unknown` and `Review` role/seniority values from categorical filters and charts.

---

# Current dashboard notes

The frontend consumes the governed Feature 9 presentation export through a static JSON contract.

The Graduate Roadmap remains intentionally partial where governed pathway-priority or learning-stage rules are unavailable. The application should show an unavailable state rather than inventing recommendations.

---

# Development commands summary

## Python

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run skill-compass --help
```

## Dashboard

```powershell
cd skill-compass-front-end
pnpm install
pnpm dev
```

## Rebuild dashboard data

```powershell
cd skill-compass-front-end
pnpm data:build
```

---

## Project scope

Skill Compass was developed as a university Data Analytics capstone project. Phase 2 focused on delivering a reproducible analytics pipeline and presentation layer using real Australian job-advertisement data.

The repository is designed so the analytical engine, configuration and presentation layers remain separated, making the project easier to maintain, reproduce and adapt.
