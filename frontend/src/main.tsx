import React from "react";
import ReactDOM from "react-dom/client";
import { Navigate, NavLink, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import CriticalPeriodsPage from "./pages/CriticalPeriodsPage";
import DataSourcesPage from "./pages/DataSourcesPage";
import FireGlobePage from "./pages/FireGlobePage";

function Header() {
  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">NASA Space Apps Challenge</p>
        <h1>FIREHARMONY</h1>
      </div>
      <nav>
        <NavLink to="/fire-map">FIRE GLOBE</NavLink>
        <NavLink to="/critical-periods">CALENDAR</NavLink>
        <NavLink to="/data-sources">SOURCES</NavLink>
      </nav>
    </header>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider>
      <Router>
        <Header />
        <Routes>
          <Route path="/" element={<Navigate to="/fire-map" replace />} />
          <Route path="/fire-map" element={<FireGlobePage />} />
          <Route path="/critical-periods" element={<CriticalPeriodsPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
        </Routes>
      </Router>
    </AppProvider>
  </React.StrictMode>,
);
