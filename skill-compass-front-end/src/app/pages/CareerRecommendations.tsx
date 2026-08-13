import { useMemo, useState } from "react";
import { colors, chartColors, InsightCard, SlicerChip } from "../components/shared";
import {
  filterJobs,
  formatPercent,
  skillDemand,
  useDashboardData,
} from "../data/dashboardData";

function UnavailablePanel({ title, children }: { title: string; children: string }) {
  return (
    <div style={{ flex: 1, background: "#fff", borderRadius: 8, padding: "12px 14px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", border: `1px solid ${colors.lightGrey}` }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 6 }}>
        <div style={{ width: 18, height: 18, borderRadius: 4, background: "#FEF3C7", color: "#92400E", display: "grid", placeItems: "center", fontSize: 10, fontWeight: 800 }}>!</div>
        <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack }}>{title}</div>
      </div>
      <div style={{ fontSize: 10, lineHeight: 1.5, color: colors.darkGrey }}>{children}</div>
      <div style={{ marginTop: 8, display: "inline-block", padding: "3px 7px", borderRadius: 4, background: "#FEF3C7", color: "#92400E", fontSize: 8, fontWeight: 700 }}>AWAITING GOVERNED PRODUCTION RULES</div>
    </div>
  );
}

export default function CareerRecommendations() {
  const { data } = useDashboardData();
  const document = data!;
  const pathways = document.views.vw_dim_pathways;
  const defaultPathway = pathways.find((row) => row.is_default === true) ?? pathways[0];
  const [selectedPathId, setSelectedPathId] = useState(String(defaultPathway?.pathway_id ?? ""));
  const selectedPath = pathways.find((row) => String(row.pathway_id) === selectedPathId) ?? defaultPathway;
  const roleId = String(selectedPath?.role_group_id ?? "");
  const profile = document.views.vw_role_profiles.find((row) => row.role_group_id === roleId);
  const roleName = profile?.role_group_name ?? String(selectedPath?.pathway_name ?? "Pathway");
  const jobs = useMemo(() => filterJobs(document, { role: roleName }), [document, roleName]);
  const graduateJobs = jobs.filter((job) => job.graduate_level_flag);
  const topSkills = skillDemand(document, jobs).slice(0, 6);
  const combinations = document.views.vw_skill_combinations
    .filter((row) => row.pathway_id === selectedPathId)
    .sort((a, b) => a.combination_rank - b.combination_rank || b.supporting_job_count - a.supporting_job_count)
    .slice(0, 6);

  return (
    <div style={{ flex: 1, background: colors.lightBg, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ background: "#fff", borderBottom: `1px solid ${colors.lightGrey}`, padding: "6px 20px", display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: colors.forestGreen, textTransform: "uppercase", marginRight: 4 }}>Choose pathway:</div>
        {pathways.map((pathway) => {
          const id = String(pathway.pathway_id);
          return <SlicerChip key={id} label={String(pathway.pathway_name)} selected={selectedPathId === id} onClick={() => setSelectedPathId(id)} />;
        })}
        <div style={{ marginLeft: "auto", fontSize: 9, color: colors.medGrey }}>Evidence-based sections only</div>
      </div>

      <div style={{ flex: 1, padding: "10px 16px", display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1.15fr 1fr 0.9fr", gap: 10, flex: 1, minHeight: 0 }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: "12px 14px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ fontSize: 9, fontWeight: 700, color: colors.forestGreen, textTransform: "uppercase", marginBottom: 3 }}>Governed role profile</div>
            <div style={{ fontSize: 16, fontWeight: 750, color: colors.nearBlack, marginBottom: 5 }}>{profile?.profile_title ?? roleName}</div>
            <div style={{ fontSize: 10, color: colors.darkGrey, lineHeight: 1.5, marginBottom: 10 }}>{profile?.profile_summary ?? "No governed role profile is available."}</div>
            {[
              ["Core skills", profile?.core_skills_text],
              ["Tool emphasis", profile?.tool_emphasis_text],
              ["Business emphasis", profile?.business_emphasis_text],
              ["Technical depth", profile?.technical_depth_text],
            ].map(([label, value], index) => (
              <div key={label} style={{ padding: "7px 8px", background: index % 2 ? "#F9FAF8" : colors.lightBg, borderRadius: 5, marginBottom: 5 }}>
                <div style={{ fontSize: 8, color: colors.medGrey, fontWeight: 700, textTransform: "uppercase" }}>{label}</div>
                <div style={{ fontSize: 9, color: colors.darkGrey, lineHeight: 1.35, marginTop: 2 }}>{value ?? "Not available"}</div>
              </div>
            ))}
          </div>

          <div style={{ background: "#fff", borderRadius: 8, padding: "12px 14px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack }}>Top Observed Skill Combinations</div>
            <div style={{ fontSize: 9, color: colors.medGrey, margin: "2px 0 8px" }}>Governed combinations for {roleName}; small-sample warnings are retained.</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6, overflow: "auto" }}>
              {combinations.map((combination, index) => (
                <div key={`${combination.combination_label}-${index}`} style={{ border: `1px solid ${colors.lightGrey}`, borderRadius: 6, padding: "7px 8px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <div style={{ fontSize: 10, fontWeight: 650, color: colors.darkGrey }}>{combination.combination_label}</div>
                    <div style={{ fontSize: 10, fontWeight: 750, color: chartColors[0] }}>{Math.round(combination.job_percentage * 100)}%</div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", marginTop: 3, fontSize: 8, color: colors.medGrey }}>
                    <span>{combination.supporting_job_count} of {combination.eligible_job_count} eligible jobs</span>
                    {combination.sample_size_warning_flag && <span style={{ color: "#92400E", fontWeight: 700 }}>SMALL SAMPLE</span>}
                  </div>
                </div>
              ))}
              {!combinations.length && <div style={{ fontSize: 10, color: colors.medGrey }}>No governed combinations are available for this pathway.</div>}
            </div>
          </div>

          <div style={{ background: colors.forestGreen, borderRadius: 8, padding: "12px 14px", color: "#fff", display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 11, fontWeight: 700, marginBottom: 8 }}>Current Market Evidence</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 7, marginBottom: 10 }}>
              {[
                ["Role jobs", jobs.length.toLocaleString()],
                ["Graduate-level", formatPercent(graduateJobs.length, jobs.length)],
                ["Top skill", topSkills[0]?.name ?? "No data"],
                ["Skill demand", topSkills[0] ? `${topSkills[0].value}%` : "—"],
              ].map(([label, value]) => (
                <div key={label} style={{ background: "rgba(255,255,255,0.1)", borderRadius: 5, padding: "7px" }}>
                  <div style={{ fontSize: 8, opacity: 0.65, textTransform: "uppercase" }}>{label}</div>
                  <div style={{ fontSize: 14, fontWeight: 750, marginTop: 2 }}>{value}</div>
                </div>
              ))}
            </div>
            <div style={{ fontSize: 9, fontWeight: 700, color: colors.limeGreen, marginBottom: 5 }}>TOP SKILLS IN ROLE</div>
            {topSkills.map((skill) => (
              <div key={skill.name} style={{ display: "flex", justifyContent: "space-between", fontSize: 9, padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,0.12)" }}>
                <span>{skill.name}</span><strong>{skill.value}%</strong>
              </div>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, flexShrink: 0 }}>
          <UnavailablePanel title="Skill Priority Matrix unavailable">Demand data exists, but governed difficulty and priority weights are not implemented. The dashboard therefore does not place skills into “learn first” or “advanced” quadrants.</UnavailablePanel>
          <UnavailablePanel title="Learning Roadmap unavailable">The production roadmap-stage contract is empty. Sequenced learning stages would be recommendations, so the prototype sequence has been removed until rules are approved.</UnavailablePanel>
        </div>

        <InsightCard bullets={[
          `${roleName} has ${jobs.length.toLocaleString()} governed job advertisements in the current snapshot, with ${formatPercent(graduateJobs.length, jobs.length)} flagged as graduate-level.`,
          combinations.some((row) => row.sample_size_warning_flag) ? "Observed combinations for this pathway carry small-sample warnings and should not be treated as universal curricula." : "Combination percentages use eligible jobs within the selected governed pathway.",
          "Skill demand and role profiles are live; difficulty scores and sequenced learning advice remain unavailable rather than being inferred.",
        ]} />
      </div>
    </div>
  );
}
