import { useMemo, useState } from "react";
import {
  colors, chartColors, KPICard, ChartCard, InsightCard,
  SlicerBar, SlicerDropdown, HBarList, DonutChart, ColumnChart,
} from "../components/shared";
import {
  countBy,
  dimensionName,
  filterJobs,
  formatPercent,
  skillDemand,
  uniqueSorted,
  useDashboardData,
} from "../data/dashboardData";

export default function ExecutiveSummary() {
  const { data } = useDashboardData();
  const document = data!;
  const [roleFilter, setRoleFilter] = useState("All Roles");
  const [locationFilter, setLocationFilter] = useState("All States");
  const [seniorityFilter, setSeniorityFilter] = useState("All Levels");
  const [empFilter, setEmpFilter] = useState("All Types");

  const jobs = useMemo(() => filterJobs(document, {
    role: roleFilter,
    state: locationFilter,
    seniority: seniorityFilter,
    employment: empFilter,
  }), [document, roleFilter, locationFilter, seniorityFilter, empFilter]);

  const roles = uniqueSorted(document.views.vw_jobs.map((job) => job.role_group_name));
  const states = uniqueSorted(document.views.vw_jobs.map((job) => job.state_code));
  const seniorities = uniqueSorted(document.views.vw_jobs.map((job) => job.seniority_name));
  const employmentTypes = uniqueSorted(document.views.vw_dim_employment_types.map((row) => String(row.employment_type_name)));
  const topSkills = skillDemand(document, jobs).slice(0, 10);
  const roleData = countBy(jobs, (job) => job.role_group_name).slice(0, 5).map((row, i) => ({ ...row, color: chartColors[i % chartColors.length] }));
  const seniorityData = countBy(jobs, (job) => job.seniority_name).map((row, i) => ({ ...row, color: chartColors[i % chartColors.length] }));
  const stateData = countBy(jobs, (job) => job.state_code).map((row, i) => ({ ...row, color: chartColors[i % chartColors.length] }));
  const employmentData = countBy(jobs, (job) => dimensionName(
    document.views.vw_dim_employment_types,
    "employment_type_id",
    "employment_type_name",
    job.primary_employment_type_id,
  )).map((row, i) => ({ ...row, color: chartColors[i % chartColors.length] }));
  const topSkill = topSkills[0];
  const topRole = roleData[0];
  const topState = stateData[0];
  const graduateCount = jobs.filter((job) => job.graduate_level_flag).length;

  return (
    <div style={{ flex: 1, background: colors.lightBg, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <SlicerBar>
        <SlicerDropdown label="Role Type" options={["All Roles", ...roles]} value={roleFilter} onChange={setRoleFilter} />
        <SlicerDropdown label="Location" options={["All States", ...states]} value={locationFilter} onChange={setLocationFilter} />
        <SlicerDropdown label="Seniority" options={["All Levels", ...seniorities]} value={seniorityFilter} onChange={setSeniorityFilter} />
        <SlicerDropdown label="Employment" options={["All Types", ...employmentTypes]} value={empFilter} onChange={setEmpFilter} />
        <div style={{ marginLeft: "auto", fontSize: 10, color: colors.medGrey }}>
          Showing: <strong style={{ color: colors.forestGreen }}>{jobs.length.toLocaleString()}</strong> job advertisements
        </div>
      </SlicerBar>

      <div style={{ flex: 1, padding: "10px 16px", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
        <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <KPICard label="Total Job Ads" value={jobs.length.toLocaleString()} accent={colors.forestGreen} />
          <KPICard label="Top Skill" value={topSkill?.name ?? "No data"} sub={topSkill ? `${topSkill.value}% of job ads` : undefined} accent={colors.limeGreen} />
          <KPICard label="Most Common Role" value={topRole?.name ?? "No data"} sub={topRole ? `${formatPercent(topRole.value, jobs.length)} of listings` : undefined} accent={colors.emerald} />
          <KPICard label="Highest Demand State" value={topState?.name ?? "No data"} sub={topState ? `${topState.value.toLocaleString()} job ads` : undefined} accent={colors.teal} />
          <KPICard label="Graduate-Level Roles" value={formatPercent(graduateCount, jobs.length)} sub={`${graduateCount.toLocaleString()} positions`} accent={colors.amber} />
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 10, overflow: "hidden" }}>
          <ChartCard title="Top 10 In-Demand Skills" style={{ gridRow: "1 / 3" }}>
            <HBarList data={topSkills} />
          </ChartCard>
          <ChartCard title="Job Ads by Role Category">
            <DonutChart data={roleData} size={110} />
          </ChartCard>
          <ChartCard title="Seniority Level Breakdown">
            <ColumnChart data={seniorityData} height={90} />
          </ChartCard>
          <ChartCard title="Jobs by State">
            <HBarList data={stateData} unit="" />
          </ChartCard>
          <ChartCard title="Employment Type Distribution">
            <DonutChart data={employmentData} size={100} />
          </ChartCard>
        </div>

        <div style={{ flexShrink: 0 }}>
          <InsightCard bullets={[
            topSkills.length >= 3 ? `${topSkills[0].name}, ${topSkills[1].name}, and ${topSkills[2].name} are the three most frequently requested skills in this filter context.` : "Skill demand is calculated from distinct job-to-skill matches.",
            roleData.length >= 2 ? `${roleData[0].name} and ${roleData[1].name} account for ${formatPercent(roleData[0].value + roleData[1].value, jobs.length)} of the selected listings.` : "Role counts use distinct job advertisements.",
            stateData.length >= 2 ? `${stateData[0].name} and ${stateData[1].name} account for ${formatPercent(stateData[0].value + stateData[1].value, jobs.length)} of the selected listings.` : "Location demand uses each job's canonical primary state.",
            "Unclassified role and seniority labels are hidden from categorical breakdowns, while overall totals retain every advertisement.",
          ]} />
        </div>
      </div>
    </div>
  );
}
