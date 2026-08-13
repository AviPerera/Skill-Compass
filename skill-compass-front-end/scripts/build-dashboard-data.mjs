/**
 * Build the static dashboard JSON from the governed Feature 9 export.
 *
 * This script belongs to the frontend delivery boundary. It copies validated
 * presentation views without modifying, recalculating, or reaching into any of
 * the nine backend feature implementations.
 */

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = resolve(scriptDirectory, "..");
const sourcePath = resolve(
  frontendDirectory,
  "../data/processed/national/powerbi/skill_compass_powerbi_live.json",
);
const outputPath = resolve(frontendDirectory, "data/dashboard-data.json");

const requiredViews = [
  "vw_dim_analysis_period",
  "vw_dim_roles",
  "vw_dim_seniority",
  "vw_dim_geography",
  "vw_dim_employment_types",
  "vw_dim_work_modes",
  "vw_dim_skills",
  "vw_dim_pathways",
  "vw_jobs",
  "vw_job_skills",
  "vw_pathway_skill_priorities",
  "vw_skill_combinations",
  "vw_role_profiles",
  "vw_roadmap_stages",
  "vw_methodology_steps",
  "vw_pipeline_metrics",
  "vw_data_quality_metrics",
  "vw_validation_metrics",
  "vw_technology_tools",
  "vw_limitations",
  "vw_project_metadata",
];

const source = JSON.parse(await readFile(sourcePath, "utf8"));

if (!source.views || typeof source.views !== "object") {
  throw new Error("Feature 9 export does not contain a views object.");
}

for (const viewName of requiredViews) {
  if (!Array.isArray(source.views[viewName])) {
    throw new Error(`Feature 9 export is missing required view: ${viewName}`);
  }
}

const dashboardDocument = {
  schema_version: "1.0.0",
  source_contract_version: source.contract?.contract_version ?? "unknown",
  data_as_of_at: source.data_as_of_at,
  source: {
    name: "Skill Compass Feature 9 Power BI export",
    path: "data/processed/national/powerbi/skill_compass_powerbi_live.json",
    privacy: "Presentation-safe export: no descriptions, evidence snippets, contacts, or tracking values.",
  },
  coverage: {
    analytical_pages: "available",
    methodology_page: "available",
    graduate_roadmap: {
      pathways: source.views.vw_dim_pathways.length > 0,
      role_profiles: source.views.vw_role_profiles.length > 0,
      skill_combinations: source.views.vw_skill_combinations.length > 0,
      pathway_skill_priorities: source.views.vw_pathway_skill_priorities.length > 0,
      roadmap_stages: source.views.vw_roadmap_stages.length > 0,
    },
  },
  views: source.views,
};

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${JSON.stringify(dashboardDocument, null, 2)}\n`, "utf8");

console.log(`Dashboard JSON written: ${outputPath}`);
console.log(`Jobs: ${source.views.vw_jobs.length}`);
console.log(`Job-skill rows: ${source.views.vw_job_skills.length}`);
