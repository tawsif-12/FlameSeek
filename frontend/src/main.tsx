import React from "react";
import ReactDOM from "react-dom/client";
import { NavLink, Navigate, Route, BrowserRouter as Router, Routes, useLocation } from "react-router-dom";
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
        <span className="brand-glyph" aria-hidden="true">
          <svg viewBox="0 0 32 32" width="32" height="32"><circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.6" /><circle cx="16" cy="16" r="4" fill="currentColor" opacity="0.9" /><ellipse cx="16" cy="16" rx="14" ry="5.5" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" /></svg>
        </span>
        <div>
          <p className="eyebrow">NASA Space Apps Challenge</p>
          <h1>FlameSeek</h1>
        </div>
      </div>
      <nav>
        <NavLink to="/">HOME</NavLink>
        <NavLink to="/fire-map">FIRE NOW</NavLink>
        <NavLink to="/fire-memory">FIRE MEMORY</NavLink>
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
