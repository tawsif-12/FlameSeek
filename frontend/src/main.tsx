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
        <h1>{isHome ? "FIREHARMONY" : "Burning Activity Calendar"}</h1>
      </div>
      <nav>
        <NavLink to="/">EARTH</NavLink>
        <NavLink to="/fire-map">FIRE MAP</NavLink>
        <a href="/#explorer">CALENDAR</a>
        <a href="/#explorer">ANALYTICS</a>
        <a href="/#explorer">ALERTS</a>
        <NavLink to="/data-sources">ABOUT</NavLink>
        <NavLink className="launch-link" to="/fire-map">LAUNCH EXPLORER</NavLink>
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
