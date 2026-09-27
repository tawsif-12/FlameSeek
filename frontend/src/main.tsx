import React from "react";
import ReactDOM from "react-dom/client";
import { NavLink, Route, BrowserRouter as Router, Routes, useLocation } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import HomePage from "./pages/HomePage";
import CriticalPeriodsPage from "./pages/CriticalPeriodsPage";
import DataSourcesPage from "./pages/DataSourcesPage";
import FireGlobePage from "./pages/FireGlobePage";

function Header() {
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <header className={isHome ? "app-header mission-header" : "app-header"}>
      <div>
        <p className="eyebrow">NASA Space Apps Challenge</p>
        <h1>FIREHARMONY</h1>
      </div>
      <nav>
        <NavLink to="/">HOME</NavLink>
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
          <Route path="/" element={<HomePage />} />
          <Route path="/fire-map" element={<FireGlobePage />} />
          <Route path="/critical-periods" element={<CriticalPeriodsPage />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
        </Routes>
      </Router>
    </AppProvider>
  </React.StrictMode>,
);
