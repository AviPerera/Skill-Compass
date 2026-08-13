import {
  createContext,
  type ReactNode,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

export interface DashboardJob {
  job_id: string;
  role_group_name: string;
  business_oriented_flag: boolean | null;
  state_code: string | null;
  state_name: string | null;
  city: string | null;
  seniority_name: string;
  graduate_level_flag: boolean;
  primary_employment_type_id: string;
  primary_work_mode_id: string;
  skill_count_total: number;
}

export interface JobSkill {
  job_id: string;
  skill_id: string;
  skill_name: string;
  skill_category_name: string;
  dashboard_group_name: string;
}

export interface NamedDimension {
  [key: string]: string | number | boolean | null;
}

export interface SkillCombination extends NamedDimension {
  pathway_id: string;
  combination_label: string;
  supporting_job_count: number;
  eligible_job_count: number;
  job_percentage: number;
  combination_rank: number;
  sample_size_warning_flag: boolean;
}

export interface RoleProfile extends NamedDimension {
  role_group_id: string;
  role_group_name: string;
  profile_title: string;
  profile_summary: string;
  core_skills_text: string;
  tool_emphasis_text: string;
  business_emphasis_text: string;
  technical_depth_text: string;
}

export interface DashboardViews {
  vw_dim_analysis_period: NamedDimension[];
  vw_dim_roles: NamedDimension[];
  vw_dim_seniority: NamedDimension[];
  vw_dim_geography: NamedDimension[];
  vw_dim_employment_types: NamedDimension[];
  vw_dim_work_modes: NamedDimension[];
  vw_dim_skills: NamedDimension[];
  vw_dim_pathways: NamedDimension[];
  vw_jobs: DashboardJob[];
  vw_job_skills: JobSkill[];
  vw_pathway_skill_priorities: NamedDimension[];
  vw_skill_combinations: SkillCombination[];
  vw_role_profiles: RoleProfile[];
  vw_roadmap_stages: NamedDimension[];
  vw_methodology_steps: NamedDimension[];
  vw_pipeline_metrics: NamedDimension[];
  vw_data_quality_metrics: NamedDimension[];
  vw_validation_metrics: NamedDimension[];
  vw_technology_tools: NamedDimension[];
  vw_limitations: NamedDimension[];
  vw_project_metadata: NamedDimension[];
  [viewName: string]: unknown[];
}

export interface DashboardDocument {
  schema_version: string;
  source_contract_version: string;
  data_as_of_at: string;
  coverage: {
    graduate_roadmap: {
      pathways: boolean;
      role_profiles: boolean;
      skill_combinations: boolean;
      pathway_skill_priorities: boolean;
      roadmap_stages: boolean;
    };
  };
  views: DashboardViews;
}

interface DashboardContextValue {
  data: DashboardDocument | null;
  error: string | null;
  isLoading: boolean;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardDataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<DashboardDocument | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    fetch(`${import.meta.env.BASE_URL}dashboard-data.json`)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Dashboard data request failed (${response.status}).`);
        }
        return response.json() as Promise<DashboardDocument>;
      })
      .then((document) => {
        if (!document.views?.vw_jobs || !document.views?.vw_job_skills) {
          throw new Error("Dashboard data is missing required analytical views.");
        }
        if (isCurrent) setData(document);
      })
      .catch((reason: unknown) => {
        if (isCurrent) {
          setError(reason instanceof Error ? reason.message : "Dashboard data could not be loaded.");
        }
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  const value = useMemo(
    () => ({ data, error, isLoading: data === null && error === null }),
    [data, error],
  );

  return <DashboardContext.Provider value={value}>{children}</DashboardContext.Provider>;
}

export function useDashboardData(): DashboardContextValue {
  const context = useContext(DashboardContext);
  if (!context) throw new Error("useDashboardData must be used inside DashboardDataProvider.");
  return context;
}

export interface JobFilters {
  role?: string;
  state?: string;
  city?: string;
  seniority?: string;
  employment?: string;
  workMode?: string;
}

function dimensionMap(
  rows: NamedDimension[],
  idField: string,
  nameField: string,
): Map<string, string> {
  return new Map(rows.map((row) => [String(row[idField]), String(row[nameField])]));
}

export function filterJobs(
  document: DashboardDocument,
  filters: JobFilters,
): DashboardJob[] {
  const employmentNames = dimensionMap(
    document.views.vw_dim_employment_types,
    "employment_type_id",
    "employment_type_name",
  );
  const workModeNames = dimensionMap(
    document.views.vw_dim_work_modes,
    "work_mode_id",
    "work_mode_name",
  );

  return document.views.vw_jobs.filter((job) => (
    (!filters.role || filters.role === "All Roles" || job.role_group_name === filters.role)
    && (!filters.state || filters.state === "All States" || job.state_code === filters.state)
    && (!filters.city || filters.city === "All Cities" || job.city === filters.city)
    && (!filters.seniority || filters.seniority === "All Levels" || job.seniority_name === filters.seniority)
    && (!filters.employment || filters.employment === "All Types" || employmentNames.get(job.primary_employment_type_id) === filters.employment)
    && (!filters.workMode || filters.workMode === "All Arrangements" || workModeNames.get(job.primary_work_mode_id) === filters.workMode)
  ));
}

export function uniqueSorted(values: Array<string | null | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b));
}

export function countBy<T>(rows: T[], getName: (row: T) => string | null | undefined) {
  const counts = new Map<string, number>();
  rows.forEach((row) => {
    const name = getName(row);
    if (name) counts.set(name, (counts.get(name) ?? 0) + 1);
  });
  return [...counts.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value || a.name.localeCompare(b.name));
}

export function skillDemand(
  document: DashboardDocument,
  jobs: DashboardJob[],
  category?: string,
) {
  const jobIds = new Set(jobs.map((job) => job.job_id));
  const skillJobs = new Map<string, Set<string>>();
  const metadata = new Map<string, JobSkill>();

  document.views.vw_job_skills.forEach((row) => {
    if (!jobIds.has(row.job_id)) return;
    if (category && category !== "All Categories"
      && row.skill_category_name !== category
      && row.dashboard_group_name !== category) return;
    if (!skillJobs.has(row.skill_name)) skillJobs.set(row.skill_name, new Set());
    skillJobs.get(row.skill_name)?.add(row.job_id);
    metadata.set(row.skill_name, row);
  });

  return [...skillJobs.entries()]
    .map(([name, ids]) => ({
      name,
      count: ids.size,
      value: jobs.length ? Math.round((ids.size / jobs.length) * 100) : 0,
      category: metadata.get(name)?.skill_category_name ?? "Unclassified",
      group: metadata.get(name)?.dashboard_group_name ?? "Unclassified",
    }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

export function dimensionName(
  rows: NamedDimension[],
  idField: string,
  nameField: string,
  id: string,
) {
  return rows.find((row) => row[idField] === id)?.[nameField]?.toString() ?? "Unknown";
}

export function formatPercent(numerator: number, denominator: number): string {
  return `${denominator ? Math.round((numerator / denominator) * 100) : 0}%`;
}

export function formatDate(value: string): string {
  return new Intl.DateTimeFormat("en-AU", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "Australia/Sydney",
  }).format(new Date(value));
}
