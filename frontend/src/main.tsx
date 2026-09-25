import React from "react";
import ReactDOM from "react-dom/client";
import { NavLink, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import HomePage from "./pages/HomePage";
import CriticalPeriodsPage from "./pages/CriticalPeriodsPage";
import DataSourcesPage from "./pages/DataSourcesPage";
import FireGlobePage from "./pages/FireGlobePage";

function Header() {
  return (
    <header className="app-header">
      <div>
        <p className="eyebrow">NASA Space Apps Challenge</p>
        <h1>Burning Activity Calendar</h1>
      </div>
      <nav>
        <NavLink to="/">Calendar</NavLink>
        <NavLink to="/fire-map">3D Fire Map</NavLink>
        <NavLink to="/critical-periods">Critical Periods</NavLink>
        <NavLink to="/data-sources">Data Sources</NavLink>
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
          <Route path="/" element={<HomePage />} />
          <Route path="/fire-map" element={<FireGlobePage />} />
          <Route path="/critical-periods" element={<CriticalPeriodsPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
        </Routes>
      </Router>
    </AppProvider>
  </React.StrictMode>,
);
