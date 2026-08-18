import { useMemo, useState } from "react";
import {
  colors, chartColors, KPICard, ChartCard, InsightCard,
  SlicerBar, SlicerDropdown, MatrixHeatmap, SlicerChip
} from "../components/shared";
import {
  countBy,
  filterJobs,
  formatPercent,
  skillDemand,
  uniqueSorted,
  useDashboardData,
} from "../data/dashboardData";

function RoleHBarChart({ data }: { data: { name: string; value: number; color: string }[] }) {
  const max = Math.max(1, ...data.map(d => d.value));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7, flex: 1, justifyContent: "space-evenly", padding: "2px 0" }}>
      {data.map((item, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ fontSize: 10, color: colors.darkGrey, width: 118, textAlign: "right", flexShrink: 0, fontWeight: 500 }}>{item.name}</div>
          <div style={{ flex: 1, background: colors.lightGrey, borderRadius: 3, height: 18, position: "relative", overflow: "visible" }}>
            <div style={{
              width: `${(item.value / max) * 100}%`,
              height: "100%",
              background: item.color,
              borderRadius: 3,
              minWidth: 4,
              display: "flex",
              alignItems: "center",
            }} />
          </div>
          <div style={{ fontSize: 10, fontWeight: 700, color: colors.nearBlack, width: 36, flexShrink: 0 }}>{item.value.toLocaleString()}</div>
        </div>
      ))}
    </div>
  );
}

function RoleColChart({
  data,
  showLegend = false,
}: {
  data: { name: string; value: number; color: string }[];
  showLegend?: boolean;
}) {
  const max = Math.max(1, ...data.map(d => d.value));
  const vbW = 300;
  const vbH = 180;
  const padL = 6;
  const padR = 6;
  const padTop = 22;
  const padBot = 28;
  const chartH = vbH - padTop - padBot;
  const totalBarW = vbW - padL - padR;
  const slotW = totalBarW / data.length;
  const barPad = slotW * 0.18;
  const barW = slotW - barPad * 2;

  const bars = data.map((d, i) => {
    const barH = Math.max((d.value / max) * chartH, 4);
    const x = padL + i * slotW + barPad;
    const y = padTop + chartH - barH;
    return { ...d, barH, barW, x, y };
  });

  return (
    <div style={{ flex: 1, display: "flex", gap: 8, overflow: "hidden", minHeight: 0 }}>
      {/* Left legend */}
      {showLegend && (
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", gap: 5, flexShrink: 0, width: 100 }}>
          {data.map((d, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <div style={{ width: 10, height: 10, borderRadius: 2, background: d.color, flexShrink: 0 }} />
              <div style={{ fontSize: 9, color: colors.darkGrey, lineHeight: 1.2 }}>{d.name}</div>
              <div style={{ marginLeft: "auto", fontSize: 10, fontWeight: 700, color: colors.nearBlack }}>{d.value}</div>
            </div>
          ))}
        </div>
      )}
      {/* SVG chart fills remaining width */}
      <svg
        viewBox={`0 0 ${vbW} ${vbH}`}
        style={{ flex: 1, height: "100%", display: "block" }}
        preserveAspectRatio="xMidYMid meet"
      >
        {bars.map((b, i) => (
          <g key={i}>
            {/* track */}
            <rect x={b.x} y={padTop} width={b.barW} height={chartH} rx={3} fill={colors.lightGrey} opacity={0.45} />
            {/* bar */}
            <rect x={b.x} y={b.y} width={b.barW} height={b.barH} rx={3} fill={b.color} />
            {/* value above */}
            <text x={b.x + b.barW / 2} y={b.y - 4} textAnchor="middle" fontSize={11} fontWeight="700" fill={colors.nearBlack}>{b.value}</text>
            {/* x label */}
            <text x={b.x + b.barW / 2} y={padTop + chartH + 14} textAnchor="middle" fontSize={9} fill={colors.medGrey}>
              {b.name.split(" ")[0]}
            </text>
            <text x={b.x + b.barW / 2} y={padTop + chartH + 24} textAnchor="middle" fontSize={8} fill={colors.medGrey}>
              {b.name.split(" ").slice(1).join(" ")}
            </text>
          </g>
        ))}
        {/* baseline */}
        <line x1={padL} y1={padTop + chartH} x2={vbW - padR} y2={padTop + chartH} stroke={colors.lightGrey} strokeWidth={1} />
      </svg>
    </div>
  );
}

export default function RoleAnalysis() {
  const { data } = useDashboardData();
  const document = data!;
  const [roleChip, setRoleChip] = useState("All Roles");
  const [senFilter, setSenFilter] = useState("All Levels");
  const [locFilter, setLocFilter] = useState("All States");
  const [empFilter, setEmpFilter] = useState("All Types");

  const roleChips = ["All Roles", ...uniqueSorted(document.views.vw_role_profiles.map((row) => row.role_group_name))];
  const seniorities = uniqueSorted(document.views.vw_jobs.map((job) => job.seniority_name));
  const states = uniqueSorted(document.views.vw_jobs.map((job) => job.state_code));
  const employmentTypes = uniqueSorted(document.views.vw_dim_employment_types.map((row) => String(row.employment_type_name)));
  const jobs = useMemo(() => filterJobs(document, {
    role: roleChip,
    seniority: senFilter,
    state: locFilter,
    employment: empFilter,
  }), [document, roleChip, senFilter, locFilter, empFilter]);
  const roleCounts = countBy(jobs, (job) => job.role_group_name);
  const roleAds = roleCounts.slice(0, 5).map((row, i) => ({ ...row, color: chartColors[i % chartColors.length] }));
  const avgSkills = roleCounts.slice(0, 5).map((role, i) => {
    const roleJobs = jobs.filter((job) => job.role_group_name === role.name);
    const average = roleJobs.length ? Math.round(roleJobs.reduce((sum, job) => sum + job.skill_count_total, 0) / roleJobs.length) : 0;
    return { name: role.name, value: average, color: chartColors[i % chartColors.length] };
  });
  const senCounts = countBy(jobs, (job) => job.seniority_name);
  const senData = senCounts.map((row, i) => ({
    name: row.name,
    value: jobs.length ? Math.round((row.value / jobs.length) * 100) : 0,
    color: chartColors[i % chartColors.length],
  }));
  const matrixCols = roleCounts.slice(0, 4).map((row) => row.name);
  const matrixRows = skillDemand(document, jobs).slice(0, 6).map((row) => row.name);
  const jobById = new Map(jobs.map((job) => [job.job_id, job]));
  const matrixData = matrixRows.map((skillName) => matrixCols.map((roleName) => {
    const roleJobCount = jobs.filter((job) => job.role_group_name === roleName).length;
    const matchedIds = new Set(document.views.vw_job_skills.filter((row) => row.skill_name === skillName && jobById.get(row.job_id)?.role_group_name === roleName).map((row) => row.job_id));
    return roleJobCount ? Math.round((matchedIds.size / roleJobCount) * 100) : 0;
  }));
  const profiles = document.views.vw_role_profiles.filter((profile) => roleChip === "All Roles" || profile.role_group_name === roleChip).slice(0, 4);
  const mostCommon = roleAds[0];
  const graduateCount = jobs.filter((job) => job.graduate_level_flag).length;
  const highestVariety = [...avgSkills].sort((a, b) => b.value - a.value)[0];
  const topBusinessRole = countBy(jobs.filter((job) => job.business_oriented_flag === true), (job) => job.role_group_name)[0];

  return (
    <div style={{ flex: 1, background: colors.lightBg, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <SlicerBar>
        <div style={{ display: "flex", gap: 6 }}>
          {roleChips.map(chip => (
            <SlicerChip key={chip} label={chip} selected={roleChip === chip} onClick={() => setRoleChip(chip)} />
          ))}
        </div>
        <div style={{ width: 1, height: 20, background: colors.lightGrey }} />
        <SlicerDropdown label="Seniority" options={["All Levels", ...seniorities]} value={senFilter} onChange={setSenFilter} />
        <SlicerDropdown label="Location" options={["All States", ...states]} value={locFilter} onChange={setLocFilter} />
        <SlicerDropdown label="Employment" options={["All Types", ...employmentTypes]} value={empFilter} onChange={setEmpFilter} />
      </SlicerBar>

      <div style={{ flex: 1, padding: "10px 16px", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
        {/* KPIs */}
        <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <KPICard label="Most Common Role" value={mostCommon?.name ?? "No data"} sub={mostCommon ? `${mostCommon.value.toLocaleString()} listings (${formatPercent(mostCommon.value, jobs.length)})` : undefined} accent={colors.forestGreen} />
          <KPICard label="Graduate-Level Roles" value={formatPercent(graduateCount, jobs.length)} sub={`${graduateCount.toLocaleString()} classified positions`} accent={colors.limeGreen} />
          <KPICard label="Highest Skill Variety" value={highestVariety?.name ?? "No data"} sub={highestVariety ? `Avg. ${highestVariety.value} skills required` : undefined} accent={colors.emerald} />
          <KPICard label="Top Business Role" value={topBusinessRole?.name ?? "No classified role"} sub={topBusinessRole ? `${topBusinessRole.value.toLocaleString()} listings` : undefined} accent={colors.teal} />
        </div>

        {/* Charts — 3-col × 2-row grid
              Col 1 (rows 1–2): Role × Skill Matrix
              Col 2 (row 1):    Job Ads by Role
              Col 3 (row 1):    Avg. Skills Required by Role
              Col 2–3 (row 2):  Seniority Split
        */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 10, overflow: "hidden" }}>

          {/* Role × Skill Matrix — col 1, both rows */}
          <ChartCard title="Role × Skill Matrix (Demand %)" style={{ gridColumn: "1 / 2", gridRow: "1 / 3" }}>
            <MatrixHeatmap rows={matrixRows} cols={matrixCols} data={matrixData} />
            <div style={{ marginTop: 8, padding: "8px", background: colors.softLime, borderRadius: 6, flexShrink: 0 }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: colors.forestGreen, marginBottom: 4 }}>ROLE PROFILES</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                {profiles.map(profile => (
                  <div key={profile.role_group_id} style={{ fontSize: 9, color: colors.darkGrey }}>
                    <strong style={{ color: colors.forestGreen }}>{profile.profile_title}:</strong> {profile.core_skills_text}
                  </div>
                ))}
              </div>
            </div>
          </ChartCard>

          {/* Job Ads by Role — col 2, row 1 */}
          <ChartCard title="Job Ads by Role" style={{ gridColumn: "2 / 3", gridRow: "1 / 2" }}>
            <RoleHBarChart data={roleAds} />
          </ChartCard>

          {/* Avg. Skills Required — col 3, row 1 */}
          <ChartCard title="Avg. Skills Required by Role" style={{ gridColumn: "3 / 4", gridRow: "1 / 2" }}>
            <RoleColChart data={avgSkills} showLegend={true} />
          </ChartCard>

          {/* Seniority Split — cols 2–3, row 2 */}
          <ChartCard title={`Seniority Split — ${roleChip}`} style={{ gridColumn: "2 / 4", gridRow: "2 / 3" }}>
            <div style={{ display: "flex", gap: 16, flex: 1, alignItems: "center", overflow: "hidden" }}>
              <div style={{ flex: 1, height: "100%", display: "flex" }}>
                <RoleColChart data={senData} showLegend={false} />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, width: 150, flexShrink: 0 }}>
                {senData.map((d, i) => (
                  <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 10 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <div style={{ width: 10, height: 10, borderRadius: 2, background: d.color }} />
                      <span style={{ color: colors.darkGrey }}>{d.name}</span>
                    </div>
                    <strong style={{ color: colors.nearBlack }}>{d.value}%</strong>
                  </div>
                ))}
                <div style={{ marginTop: 4, padding: "6px 8px", background: colors.softLime, borderRadius: 4 }}>
                  <div style={{ fontSize: 9, color: colors.forestGreen, fontWeight: 600 }}>
                    Graduate-level: {formatPercent(graduateCount, jobs.length)}
                  </div>
                  <div style={{ fontSize: 8, color: colors.darkGrey, marginTop: 1 }}>Governed graduate-level flag</div>
                </div>
              </div>
            </div>
          </ChartCard>

        </div>

        <div style={{ flexShrink: 0 }}>
          <InsightCard bullets={[
            mostCommon ? `${mostCommon.name} is the largest role group in the current filter context with ${mostCommon.value.toLocaleString()} jobs.` : "No jobs match the current filters.",
            highestVariety ? `${highestVariety.name} has the highest observed skill variety at an average of ${highestVariety.value} distinct skills per advertisement.` : "Skill variety cannot be calculated for this selection.",
            "Unclassified role and seniority labels are hidden from category comparisons, while overall totals retain every advertisement.",
          ]} />
        </div>
      </div>
    </div>
  );
}
