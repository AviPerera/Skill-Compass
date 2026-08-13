
import { createRoot } from "react-dom/client";
import App from "./app/App";
import { DashboardDataProvider } from "./app/data/dashboardData";
import "./styles/index.css";

createRoot(document.getElementById("root")!).render(
  <DashboardDataProvider>
    <App />
  </DashboardDataProvider>,
);
