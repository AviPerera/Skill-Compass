import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import dashboardDocument from "../../data/dashboard-data.json";
import App from "./App";
import {
  DashboardDataProvider,
  type DashboardDocument,
} from "./data/dashboardData";

const dashboard = dashboardDocument as unknown as DashboardDocument;
const totalJobs = dashboard.views.vw_jobs.length;
const dataAnalystJobs = dashboard.views.vw_jobs.filter((job) => job.role_group_name === "Data Analyst").length;
const dataScientistJobs = dashboard.views.vw_jobs.filter((job) => job.role_group_name === "Data Scientist").length;
const southAustralianJobs = dashboard.views.vw_jobs.filter((job) => job.state_code === "SA").length;

function renderDashboard() {
  return render(
    <DashboardDataProvider>
      <App />
    </DashboardDataProvider>,
  );
}

async function openPage(name: string) {
  await userEvent.click(await screen.findByRole("button", { name }));
}

describe("Skill Compass dashboard", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => dashboard,
    }));
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("publishes only the presentation-safe frontend data contract", () => {
    const publicDocument = dashboard as unknown as Record<string, unknown>;
    const serialized = JSON.stringify(dashboard);

    expect(publicDocument.source).toBeUndefined();
    expect(dashboard.views.vw_dim_analysis_period).toEqual([]);
    expect(dashboard.views.vw_dim_roles).toEqual([]);
    expect(dashboard.views.vw_dim_seniority).toEqual([]);
    expect(dashboard.views.vw_dim_geography).toEqual([]);
    expect(dashboard.views.vw_job_locations).toEqual([]);
    expect(dashboard.views.vw_job_employment_types).toEqual([]);
    expect(dashboard.views.vw_job_work_modes).toEqual([]);
    expect(dashboard.views.vw_data_quality_metrics).toEqual([]);
    expect(dashboard.views.vw_validation_metrics).toEqual([]);
    expect(serialized).not.toMatch(/description_html|description_text|evidence_snippet|contact_email|contact_phone|searchRequestToken|solMetadata/i);
  });

  it("loads the governed snapshot and filters the executive page", async () => {
    renderDashboard();

    expect(await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Connect with Avi Perera on LinkedIn" })).toHaveAttribute(
      "href",
      "https://www.linkedin.com/in/aviperera/",
    );
    expect(screen.getByRole("link", { name: "Connect with Avi Perera on LinkedIn" })).toHaveAttribute(
      "target",
      "_blank",
    );
    await userEvent.selectOptions(screen.getByLabelText("Role Type"), "Data Analyst");

    expect(screen.getByText(/Showing:/).parentElement).toHaveTextContent(`${dataAnalystJobs} job advertisements`);
    expect(screen.getAllByText("Data Analyst").length).toBeGreaterThan(0);
    expect(
      within(screen.getByText("Total Job Ads").parentElement!).getByText(String(dataAnalystJobs)),
    ).toBeInTheDocument();
  });

  it("applies the skill category to cards, charts, matrix, and table", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));
    await openPage("Skills Analysis");
    await userEvent.selectOptions(screen.getByLabelText("Skill Category"), "Soft Skills");

    expect(screen.getAllByText("Communication").length).toBeGreaterThan(1);
    expect(screen.getAllByText("No data")).toHaveLength(2);
    expect(screen.getAllByText("Soft Skills").length).toBeGreaterThan(0);
  });

  it("updates every role view when a role chip is selected", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));
    await openPage("Role Analysis");
    await userEvent.click(screen.getByRole("button", { name: "Data Scientist" }));

    expect(screen.getByText(`${dataScientistJobs} listings (100%)`)).toBeInTheDocument();
    expect(screen.getByText(/Data Scientist profile/)).toBeInTheDocument();
  });

  it("filters location KPIs, rankings, charts, and map", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));
    await openPage("Location Insights");
    await userEvent.selectOptions(screen.getByLabelText("State"), "SA");

    const highestDemandCard = screen.getByText("Highest Demand State").parentElement;
    expect(highestDemandCard).toHaveTextContent("SA");
    expect(highestDemandCard).toHaveTextContent(`${southAustralianJobs} job ads`);
    expect(screen.getByText("STATE RANKING").parentElement).toHaveTextContent("SA");
  });

  it("temporarily hides the Graduate Roadmap navigation entry", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));

    expect(screen.queryByRole("button", { name: "Graduate Roadmap" })).not.toBeInTheDocument();
    expect(screen.queryByText("Skill Priority Matrix unavailable")).not.toBeInTheDocument();
  });

  it("renders the governed methodology inventory", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));
    await openPage("Methodology");

    expect(screen.getByText("Implemented Data Workflow")).toBeInTheDocument();
    expect(screen.getByText("Tools & Technologies")).toBeInTheDocument();
    expect(screen.getByText("Known Limitations")).toBeInTheDocument();
    expect(screen.queryByText("Roadmap calculations pending")).not.toBeInTheDocument();
    expect(screen.getByText("Inconsistent job titles - Ex: Data Guru or Data Magician")).toBeInTheDocument();
    expect(screen.getByText("Role classification must use job descriptions and use rule based classification because titles can be ambiguous.")).toBeInTheDocument();
    expect(screen.getByText("Findings that would be valid for the analysis period may change over time.")).toBeInTheDocument();
    expect(screen.getByText("Manual Review Exclusions")).toBeInTheDocument();
    expect(screen.getByText("Jobs with uncertain relevance or classification are excluded from dashboard analysis until manually reviewed and validated.")).toBeInTheDocument();
    expect(screen.getByText("https://github.com/AviPerera/Skill-Compass")).toHaveAttribute(
      "href",
      "https://github.com/AviPerera/Skill-Compass",
    );
    expect(screen.getByRole("link", { name: "Open Skill Compass GitHub repository" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(within(screen.getByText("CURRENT JOBS").parentElement!).getByText(String(totalJobs))).toBeInTheDocument();
  });
});
