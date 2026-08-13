import { useMemo, useState } from "react";
import {
  colors, chartColors, KPICard, ChartCard, InsightCard,
  SlicerBar, SlicerDropdown, HBarList, ColumnChart, DonutChart,
} from "../components/shared";
import {
  countBy,
  dimensionName,
  filterJobs,
  formatPercent,
  uniqueSorted,
  useDashboardData,
} from "../data/dashboardData";

interface ChartDatum {
  name: string;
  value: number;
  color: string;
}

function AustraliaMap({ selectedState, stateData }: { selectedState: string; stateData: ChartDatum[] }) {
  const states: Array<[string, number, number, number, number]> = [
    ["WA", 20, 60, 120, 160],
    ["NT", 148, 30, 90, 120],
    ["QLD", 244, 30, 120, 160],
    ["SA", 148, 155, 95, 110],
    ["NSW", 248, 195, 110, 100],
    ["VIC", 248, 298, 95, 60],
    ["TAS", 290, 368, 55, 45],
    ["ACT", 328, 275, 28, 20],
  ];
  const countMap = new Map(stateData.map((state) => [state.name, state.value]));
  const max = Math.max(1, ...stateData.map((state) => state.value));
  const fillFor = (count: number) => {
    const ratio = count / max;
    if (ratio >= 0.7) return colors.forestGreen;
    if (ratio >= 0.35) return colors.limeGreen;
    if (ratio > 0) return colors.softLime;
    return "#F0FDF4";
  };

  return (
    <div style={{ display: "flex", flex: 1, gap: 8, alignItems: "center" }}>
      <svg viewBox="0 0 390 420" style={{ flex: 1, maxHeight: "100%" }}>
        {states.map(([label, x, y, width, height]) => {
          const count = countMap.get(label) ?? 0;
          const fill = fillFor(count);
          const isSelected = selectedState === label || selectedState === "All States";
          return (
            <g key={label}>
              <rect
                x={x} y={y} width={width} height={height} rx={4}
                fill={fill}
                stroke={selectedState === label ? colors.limeGreen : "#fff"}
                strokeWidth={selectedState === label ? 2.5 : 1}
                opacity={isSelected ? 1 : 0.35}
              />
              <text x={x + width / 2} y={y + height / 2 - 4} textAnchor="middle" fontSize={10} fontWeight="700" fill={count / max >= 0.7 ? "#fff" : colors.darkGrey}>{label}</text>
              <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fontSize={8} fill={count / max >= 0.7 ? "rgba(255,255,255,0.85)" : colors.medGrey}>{count ? count.toLocaleString() : "—"}</text>
            </g>
          );
        })}
        <g transform="translate(20, 390)">
          <text fontSize={8} fontWeight="600" fill={colors.medGrey} y={-6}>Relative demand within current filters</text>
          {[
            { label: "High", color: colors.forestGreen },
            { label: "Medium", color: colors.limeGreen },
            { label: "Low", color: colors.softLime },
          ].map((item, index) => (
            <g key={item.label} transform={`translate(${index * 82}, 0)`}>
              <rect width={12} height={12} rx={2} fill={item.color} />
              <text x={16} y={10} fontSize={8} fill={colors.darkGrey}>{item.label}</text>
            </g>
          ))}
        </g>
      </svg>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, width: 110, flexShrink: 0 }}>
        <div style={{ fontSize: 9, fontWeight: 700, color: colors.forestGreen, marginBottom: 2 }}>STATE RANKING</div>
        {stateData.map((state, index) => (
          <div key={state.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 10 }}>
            <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
              <div style={{ width: 14, height: 14, borderRadius: 2, background: state.color, display: "flex", alignItems: "center", justifyContent: "center" }}>
                <span style={{ fontSize: 8, fontWeight: 700, color: "#fff" }}>{index + 1}</span>
              </div>
              <span style={{ color: colors.darkGrey }}>{state.name}</span>
            </div>
            <span style={{ fontWeight: 600, color: colors.nearBlack }}>{state.value.toLocaleString()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function LocationInsights() {
  const { data } = useDashboardData();
  const document = data!;
  const [stateFilter, setStateFilter] = useState("All States");
  const [cityFilter, setCityFilter] = useState("All Cities");
  const [roleFilter, setRoleFilter] = useState("All Roles");
  const [workFilter, setWorkFilter] = useState("All Arrangements");

  const jobs = useMemo(() => filterJobs(document, {
    state: stateFilter,
    city: cityFilter,
    role: roleFilter,
    workMode: workFilter,
  }), [document, stateFilter, cityFilter, roleFilter, workFilter]);
  const states = uniqueSorted(document.views.vw_jobs.map((job) => job.state_code));
  const cities = uniqueSorted(document.views.vw_jobs.map((job) => job.city));
  const roles = uniqueSorted(document.views.vw_jobs.map((job) => job.role_group_name));
  const workModes = uniqueSorted(document.views.vw_dim_work_modes.map((row) => String(row.work_mode_name)));
  const stateData = countBy(jobs, (job) => job.state_code).map((row, index) => ({ ...row, color: chartColors[index % chartColors.length] }));
  const cityData = countBy(jobs, (job) => job.city).slice(0, 6).map((row, index) => ({ ...row, color: chartColors[index % chartColors.length] }));
  const workArrangement = countBy(jobs, (job) => dimensionName(document.views.vw_dim_work_modes, "work_mode_id", "work_mode_name", job.primary_work_mode_id)).map((row, index) => ({ ...row, color: chartColors[index % chartColors.length] }));
  const employmentData = countBy(jobs, (job) => dimensionName(document.views.vw_dim_employment_types, "employment_type_id", "employment_type_name", job.primary_employment_type_id)).map((row, index) => ({ ...row, color: chartColors[index % chartColors.length] }));
  const remoteHybrid = workArrangement.filter((row) => row.name === "Remote" || row.name === "Hybrid").reduce((sum, row) => sum + row.value, 0);
  const fullTime = employmentData.find((row) => row.name === "Full time");
  const topState = stateData[0];
  const topCity = cityData[0];

  return (
    <div style={{ flex: 1, background: colors.lightBg, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <SlicerBar>
        <SlicerDropdown label="State" options={["All States", ...states]} value={stateFilter} onChange={setStateFilter} />
        <SlicerDropdown label="City" options={["All Cities", ...cities]} value={cityFilter} onChange={setCityFilter} />
        <SlicerDropdown label="Role Type" options={["All Roles", ...roles]} value={roleFilter} onChange={setRoleFilter} />
        <SlicerDropdown label="Work Arrangement" options={["All Arrangements", ...workModes]} value={workFilter} onChange={setWorkFilter} />
      </SlicerBar>

      <div style={{ flex: 1, padding: "10px 16px", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
        <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <KPICard label="Highest Demand State" value={topState?.name ?? "No data"} sub={topState ? `${topState.value.toLocaleString()} job ads` : undefined} accent={colors.forestGreen} />
          <KPICard label="Top City" value={topCity?.name ?? "No city recorded"} sub={topCity ? `${topCity.value.toLocaleString()} listings` : undefined} accent={colors.limeGreen} />
          <KPICard label="Remote / Hybrid Roles" value={formatPercent(remoteHybrid, jobs.length)} sub={`${remoteHybrid.toLocaleString()} positions`} accent={colors.teal} />
          <KPICard label="Full-Time Roles" value={formatPercent(fullTime?.value ?? 0, jobs.length)} sub={`${(fullTime?.value ?? 0).toLocaleString()} positions`} accent={colors.emerald} />
        </div>

        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1.2fr 1fr 1fr", gridTemplateRows: "1fr 1fr", gap: 10, overflow: "hidden" }}>
          <ChartCard title="Australia Job Demand Map" style={{ gridRow: "1 / 3" }}>
            <AustraliaMap selectedState={stateFilter} stateData={stateData} />
          </ChartCard>
          <ChartCard title="Jobs by State"><HBarList data={stateData} unit="" /></ChartCard>
          <ChartCard title="Jobs by City"><ColumnChart data={cityData} height={80} /></ChartCard>
          <ChartCard title="Work Arrangement"><DonutChart data={workArrangement} size={100} /></ChartCard>
          <ChartCard title="Employment Type"><DonutChart data={employmentData} size={100} /></ChartCard>
        </div>

        <div style={{ flexShrink: 0 }}>
          <InsightCard bullets={[
            topState && topCity ? `${topState.name} is the leading state and ${topCity.name} is the leading city in the current filter context.` : "No locations match the current filters.",
            `${formatPercent(remoteHybrid, jobs.length)} of selected listings are classified as hybrid or remote.`,
            `${formatPercent(jobs.filter((job) => !job.city).length, jobs.length)} of selected jobs do not have a canonical city, while every mapped job retains its available state coverage.`,
          ]} />
        </div>
      </div>
    </div>
  );
}
