# Skill Compass Frontend

React dashboard for the Skill Compass project. The interface is based on the original Figma prototype and currently contains six report pages:

- Executive Summary
- Skills Analysis
- Role Analysis
- Location Insights
- Graduate Roadmap
- Methodology

The dashboard is intentionally kept as a small frontend project so it can be placed inside the main Python repository as `frontend/`.

## Requirements

- Node.js 20 or newer
- pnpm 10 or newer (recommended), or npm

## Run locally

```powershell
pnpm install
pnpm dev
```

Open the address printed by Vite, normally <http://localhost:5173>.

With npm, use `npm install` followed by `npm run dev`.

## Useful commands

| Command | Purpose |
| --- | --- |
| `pnpm dev` | Start the development server |
| `pnpm typecheck` | Check the TypeScript source |
| `pnpm build` | Type-check and create the production build in `dist/` |
| `pnpm preview` | Preview the production build locally |

## Project structure

```text
frontend/
├── src/
│   ├── app/
│   │   ├── components/shared.tsx  # Reusable dashboard visuals
│   │   ├── pages/                 # Six dashboard pages
│   │   └── App.tsx                # Navigation and report canvas
│   ├── styles/index.css           # Small global CSS reset
│   └── main.tsx                   # React entry point
├── index.html
├── package.json
├── pnpm-lock.yaml
├── pnpm-workspace.yaml
├── tsconfig.json
└── vite.config.ts
```

## Data integration

The six pages load the governed Feature 9 presentation export through a static
frontend JSON contract:

```text
Skill Compass Python package
        -> data/dashboard-data.json
        -> React filtering and aggregation
        -> existing dashboard components
```

Regenerate the file after a new Feature 9 export with:

```powershell
pnpm data:build
```

Vite serves `data/` as its public directory. The JSON retains the validated
presentation views, contains no descriptions, evidence snippets, contacts or
tracking values, and gives the React pages sufficient row-level facts to
recalculate role, state, city, seniority, employment, work-mode and skill
visuals.

The Graduate Roadmap is intentionally partial. Governed pathways, role profiles
and observed skill combinations are live. `vw_pathway_skill_priorities` and
`vw_roadmap_stages` are empty in the current backend contract, so the frontend
shows explicit unavailable states instead of prototype difficulty scores or
invented learning sequences.

If Python must run whenever a filter changes, expose the package through a small API and replace the JSON loader with API requests. The dashboard layout does not need to change for either approach.

## Placement in the main repository

Recommended parent structure:

```text
skill-compass/
├── pyproject.toml
├── src/skill_compass/
├── tests/
└── frontend/       # This folder
```

Keep `node_modules/` and `dist/` untracked. Both are already covered by this folder's `.gitignore`.
