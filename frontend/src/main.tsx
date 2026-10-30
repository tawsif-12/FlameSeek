import React from "react";
import ReactDOM from "react-dom/client";
import { Link, NavLink, Navigate, Route, BrowserRouter as Router, Routes, useLocation } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import HomePage from "./pages/HomePage";
import DataSourcesPage from "./pages/DataSourcesPage";
import FireGlobePage from "./pages/FireGlobePage";
import FireMemoryPage from "./pages/FireMemoryPage";

function Header() {
  const location = useLocation();
  const darkRoutes = ["/", "/fire-memory", "/data-sources"];
  const isDark = darkRoutes.includes(location.pathname);

  return (
    <header className={isDark ? "app-header mission-header" : "app-header"}>
      <div className="brand-mark">
        <span className="brand-glyph brand-flame" aria-hidden="true">🔥</span>
        <div>
          <h1>FlameSeek</h1>
          <p className="eyebrow">Global Fire Intelligence</p>
        </div>
      </div>
      <nav>
        <NavLink to="/">Home</NavLink>
        <NavLink to="/fire-map">Fire Now</NavLink>
        <NavLink to="/fire-memory">Fire Memory</NavLink>
        <NavLink to="/data-sources">Analysis <span aria-hidden="true">⌄</span></NavLink>
        <Link to="/data-sources#about">About</Link>
      </nav>
      <div className="header-tools">
        <Link to="/fire-map" className="header-search" aria-label="Search a location on Fire Now">
          <span aria-hidden="true">⌕</span> Search location…
        </Link>
        <span className="header-divider" aria-hidden="true" />
        <button type="button" className="header-icon" title="Alerts are coming soon" aria-label="Alerts coming soon">♧</button>
        <Link to="/data-sources" className="header-avatar" aria-label="About FlameSeek">●</Link>
      </div>
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
          <Route path="/fire-memory" element={<FireMemoryPage />} />
          <Route path="/critical-periods" element={<Navigate to="/fire-memory" replace />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
        </Routes>
      </Router>
    </AppProvider>
  </React.StrictMode>,
);
