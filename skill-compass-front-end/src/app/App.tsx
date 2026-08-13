import { useEffect, useState } from "react";
import { ReportHeader } from "./components/shared";
import ExecutiveSummary from "./pages/ExecutiveSummary";
import SkillsAnalysis from "./pages/SkillsAnalysis";
import RoleAnalysis from "./pages/RoleAnalysis";
import LocationInsights from "./pages/LocationInsights";
import CareerRecommendations from "./pages/CareerRecommendations";
import Methodology from "./pages/Methodology";
import { formatDate, useDashboardData } from "./data/dashboardData";

const CANVAS_W = 1280;
const CANVAS_H = 720;

const pages = [
  { label: "Executive Summary", component: ExecutiveSummary },
  { label: "Skills Analysis", component: SkillsAnalysis },
  { label: "Role Analysis", component: RoleAnalysis },
  { label: "Location Insights", component: LocationInsights },
  { label: "Graduate Roadmap", component: CareerRecommendations },
  { label: "Methodology", component: Methodology },
];

export default function App() {
  const { data, error, isLoading } = useDashboardData();
  const [currentPage, setCurrentPage] = useState(0);
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const updateScale = () => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const s = Math.min(vw / CANVAS_W, vh / CANVAS_H);
      setScale(s);
    };
    updateScale();
    window.addEventListener("resize", updateScale);
    return () => window.removeEventListener("resize", updateScale);
  }, []);

  const PageComponent = pages[currentPage].component;

  if (isLoading || error || !data) {
    return (
      <div style={{ width: "100vw", height: "100vh", display: "grid", placeItems: "center", background: "#F8FAF5", color: "#14532D", fontFamily: "'Segoe UI', Inter, system-ui, sans-serif" }}>
        <div style={{ padding: 24, background: "#fff", borderRadius: 8, boxShadow: "0 2px 12px rgba(0,0,0,0.12)", maxWidth: 460 }}>
          <strong>{error ? "Dashboard data unavailable" : "Loading governed dashboard data…"}</strong>
          {error && <div style={{ marginTop: 8, color: "#64748B", fontSize: 13 }}>{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        width: "100vw",
        height: "100vh",
        background: "#374151",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        fontFamily: "'Segoe UI', Inter, system-ui, sans-serif",
      }}
    >
      <div
        style={{
          width: CANVAS_W,
          height: CANVAS_H,
          transform: `scale(${scale})`,
          transformOrigin: "center center",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          boxShadow: "0 8px 40px rgba(0,0,0,0.45)",
        }}
      >
        <ReportHeader
          pageTitle={pages[currentPage].label}
          currentPage={currentPage}
          onPageChange={setCurrentPage}
          dataAsOf={formatDate(data.data_as_of_at)}
          totalJobs={data.views.vw_jobs.length}
        />
        <PageComponent />
      </div>
    </div>
  );
}
