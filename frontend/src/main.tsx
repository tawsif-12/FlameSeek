import React from "react";
import ReactDOM from "react-dom/client";
import { NavLink, Navigate, Route, BrowserRouter as Router, Routes, useLocation } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import DataSourcesPage from "./pages/DataSourcesPage";
import FireMemoryPage from "./pages/FireMemoryPage";

function Header() {
  const location = useLocation();
  const darkRoutes = ["/", "/data-sources"];
  const isDark = darkRoutes.includes(location.pathname);

  return (
    <header className={isDark ? "app-header mission-header" : "app-header"}>
      <div className="brand-mark">
        <span className="brand-glyph" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="32" height="32"><circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.6" /><circle cx="16" cy="16" r="4" fill="currentColor" opacity="0.9" /><ellipse cx="16" cy="16" rx="14" ry="5.5" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" /></svg>
        </span>
        <div>
          <p className="eyebrow">NASA Space Apps Challenge</p>
          <h1>FlameSeek</h1>
        </div>
      </div>
      <nav>
        <NavLink to="/">BURNING CALENDAR</NavLink>
        <NavLink to="/data-sources">SOURCES & METHODS</NavLink>
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
          <Route path="/" element={<FireMemoryPage />} />
          <Route path="/fire-memory" element={<Navigate to="/" replace />} />
          <Route path="/fire-map" element={<Navigate to="/" replace />} />
          <Route path="/critical-periods" element={<Navigate to="/" replace />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
        </Routes>
      </Router>
    </AppProvider>
  </React.StrictMode>,
);
