import { colors, chartColors } from "../components/shared";
import { formatDate, useDashboardData } from "../data/dashboardData";

const repositoryUrl = "https://github.com/AviPerera/Skill-Compass";

export default function Methodology() {
  const { data } = useDashboardData();
  const document = data!;
  const steps = [...document.views.vw_methodology_steps].sort((a, b) => Number(a.step_order) - Number(b.step_order));
  const tools = [...document.views.vw_technology_tools].sort((a, b) => Number(a.sort_order) - Number(b.sort_order));
  const limitations = [...document.views.vw_limitations].sort((a, b) => Number(a.sort_order) - Number(b.sort_order));
  const metadata = document.views.vw_project_metadata[0];
  const pipeline = [...document.views.vw_pipeline_metrics].sort((a, b) => Number(a.step_order) - Number(b.step_order));
  const completedSteps = pipeline.filter((row) => row.status === "completed" || row.status === "success").length;

  return (
    <div style={{ flex: 1, background: colors.lightBg, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ flex: 1, padding: "12px 16px", display: "flex", gap: 12, overflow: "hidden" }}>
        <div style={{ flex: 1.6, display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: "10px 14px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flexShrink: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack }}>Implemented Data Workflow</div>
              <div style={{ fontSize: 9, color: colors.medGrey }}>{completedSteps}/{pipeline.length} recorded pipeline steps complete</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
              {steps.map((step, index) => (
                <div key={String(step.step_code)} style={{ display: "contents" }}>
                  <div style={{ flex: 1, background: index === steps.length - 1 ? colors.softLime : colors.lightBg, border: `1px solid ${index === steps.length - 1 ? "#BEF264" : colors.lightGrey}`, borderRadius: 6, padding: "7px 6px", textAlign: "center" }}>
                    <div style={{ fontSize: 8, fontWeight: 750, color: colors.forestGreen }}>0{step.step_order}</div>
                    <div style={{ fontSize: 9, fontWeight: 600, color: colors.darkGrey, lineHeight: 1.2 }}>{step.step_name}</div>
                  </div>
                  {index < steps.length - 1 && <div style={{ color: colors.medGrey, fontSize: 12 }}>→</div>}
                </div>
              ))}
            </div>
          </div>

          <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, overflow: "hidden" }}>
            {steps.map((step, index) => {
              const run = pipeline.find((row) => row.step_code === step.step_code);
              return (
                <div key={String(step.step_code)} style={{ background: "#fff", borderRadius: 8, padding: "10px 12px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", borderLeft: `4px solid ${chartColors[index % chartColors.length]}`, display: "flex", flexDirection: "column" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 22, height: 22, borderRadius: 4, background: chartColors[index % chartColors.length], display: "grid", placeItems: "center", fontSize: 9, fontWeight: 700, color: "#fff" }}>{String(step.step_order).padStart(2, "0")}</div>
                      <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack }}>{step.step_name}</div>
                    </div>
                    <div style={{ fontSize: 8, fontWeight: 600, color: chartColors[index % chartColors.length], background: `${chartColors[index % chartColors.length]}18`, padding: "2px 6px", borderRadius: 3 }}>{step.method_tag}</div>
                  </div>
                  <div style={{ fontSize: 10, color: colors.darkGrey, lineHeight: 1.45 }}>{step.step_description}</div>
                  {run && <div style={{ marginTop: "auto", paddingTop: 5, fontSize: 8, color: colors.medGrey }}>{Number(run.input_record_count).toLocaleString()} input → {Number(run.output_record_count).toLocaleString()} output · {String(run.status)}</div>}
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ width: 300, flexShrink: 0, display: "flex", flexDirection: "column", gap: 10, overflow: "hidden" }}>
          <div style={{ background: "#fff", borderRadius: 8, padding: "10px 12px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack, marginBottom: 8 }}>Tools & Technologies</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {tools.map((tool, index) => (
                <div key={String(tool.tool_name)} style={{ display: "flex", alignItems: "center", gap: 7, padding: "4px 7px", background: "#FAFAFA", borderRadius: 5, border: `1px solid ${colors.lightGrey}` }}>
                  <div style={{ width: 8, height: 8, borderRadius: 2, background: chartColors[index % chartColors.length], flexShrink: 0 }} />
                  <div style={{ fontSize: 9, fontWeight: 600, color: colors.nearBlack, width: 72, flexShrink: 0 }}>{tool.tool_name}</div>
                  <div style={{ fontSize: 9, color: colors.medGrey, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{tool.purpose}</div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: "#fff", borderRadius: 8, padding: "10px 12px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: 1, minHeight: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack, marginBottom: 8 }}>Known Limitations</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, overflowY: "auto", paddingRight: 4 }}>
              {limitations.map((limitation) => (
                <div key={String(limitation.limitation_code)} style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
                  <div style={{ width: 16, height: 16, borderRadius: 3, flexShrink: 0, background: "#FEF3C7", border: "1px solid #FDE68A", display: "grid", placeItems: "center", fontSize: 9, fontWeight: 700, color: "#92400E", marginTop: 1 }}>!</div>
                  <div>
                    <div style={{ fontSize: 9, fontWeight: 700, color: colors.darkGrey }}>{limitation.limitation_title}</div>
                    <div style={{ fontSize: 8, color: colors.medGrey, lineHeight: 1.3 }}>{limitation.limitation_text}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ background: colors.softLime, border: "1px solid #BEF264", borderRadius: 8, padding: "10px 12px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: colors.nearBlack, marginBottom: 5 }}>Project Repository</div>
            <a
              href={repositoryUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "block", marginBottom: 7, color: colors.forestGreen, fontSize: 8, fontWeight: 600, overflowWrap: "anywhere" }}
            >
              {repositoryUrl}
            </a>
            <a
              href={repositoryUrl}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Open Skill Compass GitHub repository"
              style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 7, padding: "7px 10px", borderRadius: 5, background: "#24292F", color: "#fff", fontSize: 9, fontWeight: 700, textDecoration: "none" }}
            >
              <svg aria-hidden="true" viewBox="0 0 24 24" width="15" height="15" fill="currentColor">
                <path d="M12 .7A11.5 11.5 0 0 0 8.36 23.1c.58.1.79-.25.79-.56v-2.23c-3.24.7-3.92-1.37-3.92-1.37-.53-1.35-1.29-1.71-1.29-1.71-1.05-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.78 2.72 1.27 3.38.97.1-.75.41-1.27.74-1.56-2.58-.29-5.3-1.29-5.3-5.69 0-1.26.45-2.28 1.19-3.09-.12-.29-.52-1.47.11-3.05 0 0 .97-.31 3.16 1.18a10.9 10.9 0 0 1 5.76 0C17.03 4.99 18 5.3 18 5.3c.63 1.58.23 2.76.11 3.05.74.81 1.19 1.83 1.19 3.09 0 4.41-2.72 5.39-5.31 5.68.42.36.79 1.07.79 2.16v3.26c0 .31.21.67.8.56A11.5 11.5 0 0 0 12 .7Z" />
              </svg>
              View on GitHub
            </a>
          </div>

          <div style={{ background: colors.forestGreen, borderRadius: 8, padding: "10px 12px", flexShrink: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#fff", marginBottom: 4 }}>{metadata?.project_name ?? "Skill Compass"}</div>
            <div style={{ fontSize: 9, color: "rgba(255,255,255,0.8)", lineHeight: 1.45 }}>{metadata?.project_description}</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 5, marginTop: 8 }}>
              <div style={{ background: "rgba(255,255,255,0.1)", padding: 5, borderRadius: 4 }}><div style={{ fontSize: 7, color: "rgba(255,255,255,0.6)" }}>DATA AS OF</div><div style={{ fontSize: 9, fontWeight: 700, color: "#fff" }}>{formatDate(document.data_as_of_at)}</div></div>
              <div style={{ background: "rgba(255,255,255,0.1)", padding: 5, borderRadius: 4 }}><div style={{ fontSize: 7, color: "rgba(255,255,255,0.6)" }}>CURRENT JOBS</div><div style={{ fontSize: 9, fontWeight: 700, color: "#fff" }}>{document.views.vw_jobs.length.toLocaleString()}</div></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
