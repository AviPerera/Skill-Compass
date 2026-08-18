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
  "vw_job_locations",
  "vw_job_employment_types",
  "vw_job_work_modes",
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

const excludedClassificationLabels = new Set(["Review", "Unknown"]);
const jobs = source.views.vw_jobs.map((job) => ({
  ...job,
  role_group_name: excludedClassificationLabels.has(job.role_group_name)
    ? ""
    : job.role_group_name,
  seniority_name: excludedClassificationLabels.has(job.seniority_name)
    ? ""
    : job.seniority_name,
}));
const includedJobIds = new Set(jobs.map((job) => job.job_id));
const filterJobBridge = (viewName) => source.views[viewName].filter(
  (row) => includedJobIds.has(row.job_id),
);
const pick = (row, fields) => Object.fromEntries(
  fields.map((field) => [field, row[field]]),
);
const views = {
  vw_dim_analysis_period: source.views.vw_dim_analysis_period,
  vw_dim_roles: source.views.vw_dim_roles
    .filter((row) => !excludedClassificationLabels.has(row.role_group_name))
    .map((row) => pick(row, [
      "role_group_id", "role_group_name", "business_oriented_flag",
      "graduate_friendly_flag", "supported_pathway_flag", "sort_order",
    ])),
  vw_dim_seniority: source.views.vw_dim_seniority
    .filter((row) => !excludedClassificationLabels.has(row.seniority_name))
    .map((row) => pick(row, [
      "seniority_level_id", "seniority_name", "rank_order",
      "graduate_level_flag",
    ])),
  vw_dim_geography: source.views.vw_dim_geography,
  vw_dim_employment_types: source.views.vw_dim_employment_types.map((row) => pick(row, [
    "employment_type_id", "employment_type_name", "sort_order",
  ])),
  vw_dim_work_modes: source.views.vw_dim_work_modes.map((row) => pick(row, [
    "work_mode_id", "work_mode_name", "sort_order",
  ])),
  vw_dim_skills: source.views.vw_dim_skills.map((row) => pick(row, [
    "skill_id", "skill_name", "skill_category_name", "dashboard_group_name",
    "sort_order", "is_active",
  ])),
  vw_dim_pathways: source.views.vw_dim_pathways.map((row) => pick(row, [
    "pathway_id", "role_group_id", "pathway_name", "pathway_description",
    "recommendation_text", "is_default", "sort_order",
  ])),
  vw_jobs: jobs.map((row) => pick(row, [
    "job_id", "role_group_name", "business_oriented_flag", "state_code",
    "state_name", "city", "seniority_name", "graduate_level_flag",
    "primary_employment_type_id", "primary_work_mode_id", "skill_count_total",
  ])),
  vw_job_skills: filterJobBridge("vw_job_skills").map((row) => pick(row, [
    "job_id", "skill_id", "skill_name", "skill_category_name",
    "dashboard_group_name",
  ])),
  vw_job_locations: filterJobBridge("vw_job_locations").map((row) => pick(row, [
    "job_id", "geography_id", "is_primary",
  ])),
  vw_job_employment_types: filterJobBridge("vw_job_employment_types").map((row) => pick(row, [
    "job_id", "employment_type_id", "is_primary",
  ])),
  vw_job_work_modes: filterJobBridge("vw_job_work_modes").map((row) => pick(row, [
    "job_id", "work_mode_id", "is_primary",
  ])),
  vw_pathway_skill_priorities: source.views.vw_pathway_skill_priorities,
  vw_skill_combinations: source.views.vw_skill_combinations.map((row) => pick(row, [
    "pathway_id", "combination_label", "supporting_job_count",
    "eligible_job_count", "job_percentage", "combination_rank",
    "sample_size_warning_flag",
  ])),
  vw_role_profiles: source.views.vw_role_profiles.map((row) => pick(row, [
    "role_group_id", "role_group_name", "profile_title", "profile_summary",
    "core_skills_text", "tool_emphasis_text", "business_emphasis_text",
    "technical_depth_text",
  ])),
  vw_roadmap_stages: source.views.vw_roadmap_stages,
  vw_methodology_steps: source.views.vw_methodology_steps.map((row) => pick(row, [
    "step_order", "step_code", "step_name", "step_description", "method_tag",
  ])),
  vw_pipeline_metrics: source.views.vw_pipeline_metrics.map((row) => pick(row, [
    "step_code", "step_order", "input_record_count", "output_record_count",
    "status",
  ])),
  vw_data_quality_metrics: source.views.vw_data_quality_metrics.filter(
    (row) => !/\b(review|unknown)\b/i.test(JSON.stringify(row)),
  ),
  vw_validation_metrics: source.views.vw_validation_metrics,
  vw_technology_tools: source.views.vw_technology_tools.map((row) => pick(row, [
    "tool_name", "purpose", "implementation_status", "sort_order",
  ])),
  vw_limitations: source.views.vw_limitations
    .filter((row) => !/\b(review|unknown)\b/i.test(`${row.limitation_title} ${row.limitation_text}`))
    .map((row) => pick(row, [
      "limitation_code", "limitation_title", "limitation_text", "severity",
      "sort_order",
    ])),
  vw_project_metadata: source.views.vw_project_metadata.map((row) => pick(row, [
    "project_name", "project_description", "methodology_version",
    "architecture_version", "data_as_of_at", "collection_start_date",
    "collection_end_date",
  ])),
};

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
  views,
};

const serializedDocument = `${JSON.stringify(dashboardDocument, null, 2)}\n`;
if (/\b(review|unknown)\b/i.test(serializedDocument)) {
  throw new Error("Dashboard export still contains an excluded classification label.");
}

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, serializedDocument, "utf8");

console.log(`Dashboard JSON written: ${outputPath}`);
console.log(`Jobs: ${views.vw_jobs.length}`);
console.log(`Job-skill rows: ${views.vw_job_skills.length}`);
