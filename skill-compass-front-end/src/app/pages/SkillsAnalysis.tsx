import { useMemo, useState } from "react";
import {
  colors, chartColors, KPICard, ChartCard, InsightCard,
  SlicerBar, SlicerDropdown, HBarList, MatrixHeatmap, SimpleTable,
} from "../components/shared";
import {
  countBy,
  filterJobs,
  skillDemand,
  uniqueSorted,
  useDashboardData,
} from "../data/dashboardData";

export default function SkillsAnalysis() {
  const { data } = useDashboardData();
  const document = data!;
  const [catFilter, setCatFilter] = useState("All Categories");
  const [roleFilter, setRoleFilter] = useState("All Roles");
  const [senFilter, setSenFilter] = useState("All Levels");
  const [locFilter, setLocFilter] = useState("All States");

  const jobs = useMemo(() => filterJobs(document, {
    role: roleFilter,
    seniority: senFilter,
    state: locFilter,
  }), [document, roleFilter, senFilter, locFilter]);

  const roles = uniqueSorted(document.views.vw_jobs.map((job) => job.role_group_name));
  const seniorities = uniqueSorted(document.views.vw_jobs.map((job) => job.seniority_name));
  const states = uniqueSorted(document.views.vw_jobs.map((job) => job.state_code));
  const categories = uniqueSorted(document.views.vw_dim_skills.map((row) => String(row.skill_category_name)));
  const allDemand = skillDemand(document, jobs);
  const displayedDemand = skillDemand(document, jobs, catFilter);
  const activeDemand = catFilter === "All Categories" ? allDemand : displayedDemand;
  const technicalSkills = activeDemand.filter((row) => row.group !== "Soft Skills").slice(0, 8).map((row) => ({ ...row, color: chartColors[0] }));
  const softSkills = activeDemand.filter((row) => row.group === "Soft Skills").slice(0, 7).map((row) => ({ ...row, color: chartColors[2] }));
  const topVisualisation = activeDemand.find((row) => row.category === "Business Intelligence and Visualisation");
  const topProgramming = activeDemand.find((row) => row.category === "Programming");
  const topSoftSkill = softSkills[0];

  const matrixCols = countBy(jobs, (job) => job.role_group_name).slice(0, 4).map((row) => row.name);
  const matrixRows = activeDemand.slice(0, 7).map((row) => row.name);
  const jobById = new Map(jobs.map((job) => [job.job_id, job]));
  const matrixData = matrixRows.map((skillName) => matrixCols.map((roleName) => {
    const roleJobs = jobs.filter((job) => job.role_group_name === roleName);
    const matchedIds = new Set(document.views.vw_job_skills
      .filter((row) => row.skill_name === skillName && jobById.get(row.job_id)?.role_group_name === roleName)
      .map((row) => row.job_id));
    return roleJobs.length ? Math.round((matchedIds.size / roleJobs.length) * 100) : 0;
  }));

  const tableRows = displayedDemand.slice(0, 10).map((skill, index) => {
    const matchedJobIds = new Set(document.views.vw_job_skills.filter((row) => row.skill_name === skill.name).map((row) => row.job_id));
    const commonRoles = countBy(jobs.filter((job) => matchedJobIds.has(job.job_id)), (job) => job.role_group_name).slice(0, 2).map((row) => row.name).join(", ");
    return [String(index + 1), skill.name, skill.category, `${skill.value}%`, commonRoles || "No matches", skill.count.toLocaleString()];
  });

  return (
    <div className="dashboard-page" style={{ flex: 1, background: colors.lightBg, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <SlicerBar>
        <SlicerDropdown label="Skill Category" options={["All Categories", ...categories]} value={catFilter} onChange={setCatFilter} />
        <SlicerDropdown label="Role Type" options={["All Roles", ...roles]} value={roleFilter} onChange={setRoleFilter} />
        <SlicerDropdown label="Seniority" options={["All Levels", ...seniorities]} value={senFilter} onChange={setSenFilter} />
        <SlicerDropdown label="Location" options={["All States", ...states]} value={locFilter} onChange={setLocFilter} />
      </SlicerBar>

      <div className="page-content" style={{ flex: 1, padding: "10px 16px", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
        <div className="kpi-grid" style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <KPICard label="Most In-Demand Skill" value={activeDemand[0]?.name ?? "No data"} sub={activeDemand[0] ? `${activeDemand[0].value}% of ${jobs.length} jobs` : undefined} accent={colors.forestGreen} />
          <KPICard label="Top Visualisation Skill" value={topVisualisation?.name ?? "No data"} sub={topVisualisation ? `${topVisualisation.value}% of job ads` : undefined} accent={colors.limeGreen} />
          <KPICard label="Top Programming Skill" value={topProgramming?.name ?? "No data"} sub={topProgramming ? `${topProgramming.value}% of job ads` : undefined} accent={colors.emerald} />
          <KPICard label="Top Soft Skill" value={topSoftSkill?.name ?? "No data"} sub={topSoftSkill ? `${topSoftSkill.value}% of job ads` : undefined} accent={colors.teal} />
        </div>

        <div className="chart-grid skills-grid" style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1.4fr", gridTemplateRows: "1fr 1fr", gap: 10, overflow: "hidden" }}>
          <ChartCard title="Technical & Business Skills — Demand %" style={{ gridRow: "1 / 2" }}>
            <HBarList data={technicalSkills} />
          </ChartCard>
          <ChartCard title="Soft Skills — Demand %" style={{ gridRow: "1 / 2" }}>
            <HBarList data={softSkills} />
          </ChartCard>
          <ChartCard title="Skills × Role Matrix (Demand %)" style={{ gridRow: "1 / 3" }}>
            <MatrixHeatmap rows={matrixRows} cols={matrixCols} data={matrixData} />
            <div style={{ marginTop: 6, display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
              <div style={{ fontSize: 9, color: colors.medGrey, fontWeight: 600 }}>Distinct jobs:</div>
              <span style={{ fontSize: 9, color: colors.darkGrey }}>each cell is the share of jobs in that role requiring the skill</span>
            </div>
          </ChartCard>
          <ChartCard title="Skill Ranking Table" style={{ gridColumn: "1 / 3", gridRow: "2 / 3" }}>
            <SimpleTable
              columns={["#", "Skill", "Category", "Demand %", "Common Roles", "Jobs"]}
              rows={tableRows}
              accentCol={1}
            />
          </ChartCard>
        </div>

        <div className="insight-section" style={{ flexShrink: 0 }}>
          <InsightCard bullets={[
            activeDemand[0] ? `${activeDemand[0].name} is the leading requirement, appearing in ${activeDemand[0].value}% of the selected job advertisements.` : "No skills match the current filters.",
            topVisualisation ? `${topVisualisation.name} leads the governed Business Intelligence and Visualisation category.` : "No visualisation skill is present in this filter context.",
            `Demand rates use distinct job advertisements as the denominator; repeated mentions do not inflate a skill's result.`,
          ]} />
        </div>
      </div>
    </div>
  );
}
