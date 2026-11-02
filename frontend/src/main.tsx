import React from "react";
import ReactDOM from "react-dom/client";
import { Link, NavLink, Navigate, Route, BrowserRouter as Router, Routes } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import HomePage from "./pages/HomePage";
import DataSourcesPage from "./pages/DataSourcesPage";
import FireGlobePage from "./pages/FireGlobePage";
import FireMemoryPage from "./pages/FireMemoryPage";
import FireDnaPage from "./pages/FireDnaPage";
import SearchPage from "./pages/SearchPage";

function Header() {
  return (
    <header className="app-header mission-header">
      <Link to="/" className="brand-mark" style={{ textDecoration: "none" }}>
        <span className="brand-glyph brand-flame" aria-hidden="true">🔥</span>
        <div>
          <h1>FlameSeek</h1>
          <p className="eyebrow">Global Fire Intelligence</p>
        </div>
      </Link>
      <nav>
        <NavLink to="/fire-map">FireNow</NavLink>
        <NavLink to="/search">Search</NavLink>
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
          <Route path="/search" element={<SearchPage />} />
          <Route path="/fire-memory" element={<FireMemoryPage />} />
          <Route path="/fire-dna" element={<FireDnaPage />} />
          <Route path="/fire-calendar" element={<FireMemoryPage />} />
          <Route path="/critical-periods" element={<Navigate to="/fire-memory" replace />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
        </Routes>
      </Router>
    </AppProvider>
  </React.StrictMode>,
);
