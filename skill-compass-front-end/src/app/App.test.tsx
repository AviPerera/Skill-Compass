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

  it("loads the governed snapshot and filters the executive page", async () => {
    renderDashboard();

    expect(await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`))).toBeInTheDocument();
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

  it("switches governed pathway evidence and preserves unavailable states", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));
    await openPage("Graduate Roadmap");
    await userEvent.click(screen.getByRole("button", { name: "Business Analyst" }));

    expect(screen.getByText("Business Analyst profile")).toBeInTheDocument();
    expect(screen.getByText("Skill Priority Matrix unavailable")).toBeInTheDocument();
    expect(screen.getByText("Learning Roadmap unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("SMALL SAMPLE").length).toBeGreaterThan(0);
  });

  it("renders the governed methodology inventory", async () => {
    renderDashboard();
    await screen.findByText(new RegExp(`${totalJobs} Eligible & Relevant Jobs Analysed`));
    await openPage("Methodology");

    expect(screen.getByText("Implemented Data Workflow")).toBeInTheDocument();
    expect(screen.getByText("Tools & Technologies")).toBeInTheDocument();
    expect(screen.getByText("Known Limitations")).toBeInTheDocument();
    expect(within(screen.getByText("CURRENT JOBS").parentElement!).getByText(String(totalJobs))).toBeInTheDocument();
  });
});
