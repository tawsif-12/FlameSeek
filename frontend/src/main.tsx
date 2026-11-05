import React from "react";
import ReactDOM from "react-dom/client";
import { Link, NavLink, Navigate, Route, BrowserRouter as Router, Routes, useLocation } from "react-router-dom";
import "leaflet/dist/leaflet.css";
import "leaflet-draw/dist/leaflet.draw.css";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import HomePage from "./pages/HomePage";
import { LanguageProvider, useLanguage } from "./context/LanguageContext";
import ThemeToggle from "./components/ThemeToggle";
import "./theme.css";

const PRIMARY_NAVIGATION = [
  { to: "/", label: "Home", end: true },
  { to: "/fire-map", label: "Fire Now" },
  { to: "/search", label: "Search" },
  { to: "/fire-memory", label: "Memory" },
] as const;

const MORE_NAVIGATION = [
  { to: "/fire-dna", label: "Fire DNA" },
  { to: "/fire-events", label: "Events" },
  { to: "/data-sources", label: "Sources" },
  { to: "/methodology", label: "Methodology" },
  { to: "/about", label: "About" },
] as const;

const AREA_NAVIGATION = [
  { to: "/fire-memory", label: "Fire Memory" },
  { to: "/fire-dna", label: "Fire DNA" },
  { to: "/fire-calendar", label: "Burning Calendar" },
] as const;

// Download map engines and analysis charts only when their route is opened.
const DataSourcesPage = React.lazy(() => import("./pages/DataSourcesPage"));
const FireGlobePage = React.lazy(() => import("./pages/FireGlobePage"));
const FireMemoryPage = React.lazy(() => import("./pages/FireMemoryPage"));
const FireDnaPage = React.lazy(() => import("./pages/FireDnaPage"));
const SearchPage = React.lazy(() => import("./pages/SearchPage"));
const HarmonizedMapPage = React.lazy(() => import("./pages/HarmonizedMapPage"));
const MethodologyPage = React.lazy(() => import("./pages/MethodologyPage"));
const AboutPage = React.lazy(() => import("./pages/AboutPage"));
const AreaIntelligencePage = React.lazy(() => import("./pages/AreaIntelligencePage"));

function LanguageToggle() {
  const { lang, setLang, t } = useLanguage();
  return (
    <button className="header-language" type="button" aria-label="Switch language English / Bangla" onClick={() => setLang(lang === "en" ? "bn" : "en")}>
      {t("toggle")}
    </button>
  );
}

function Header() {
  const location = useLocation();
  const isAreaMode = ["/area", "/fire-memory", "/fire-dna", "/fire-calendar"].some(
    (prefix) => location.pathname === prefix || location.pathname.startsWith(prefix)
  );

  return (
    <header className="app-header mission-header">
      <Link to="/" className="brand-mark" style={{ textDecoration: "none" }}>
        <span className="brand-glyph brand-flame" aria-hidden="true">🔥</span>
        <div>
          <h1>FlameSeek</h1>
          <p className="eyebrow">Global Fire Intelligence</p>
        </div>
      </Link>
      <nav className="primary-navigation" aria-label="Primary navigation">
        {isAreaMode ? (
          AREA_NAVIGATION.map((item) => (
            <NavLink key={item.to} to={item.to}>
              {item.label}
            </NavLink>
          ))
        ) : (
          <>
            {PRIMARY_NAVIGATION.map((item) => (
              <NavLink key={item.to} to={item.to} end={"end" in item ? item.end : undefined}>
                {item.label}
              </NavLink>
            ))}
            <details className="header-more">
              <summary>More <span aria-hidden="true">▾</span></summary>
              <div>
                {MORE_NAVIGATION.map((item) => (
                  <NavLink key={item.to} to={item.to} onClick={(event) => event.currentTarget.closest("details")?.removeAttribute("open")}>
                    {item.label}
                  </NavLink>
                ))}
              </div>
            </details>
          </>
        )}
      </nav>
      <div className="header-actions">
        <LanguageToggle />
        <ThemeToggle />
      </div>
    </header>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppProvider>
      <LanguageProvider>
      <Router>
        <Header />
        <React.Suspense fallback={<main className="content-page" role="status">Loading page…</main>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/fire-map" element={<FireGlobePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/fire-memory" element={<FireMemoryPage />} />
          <Route path="/fire-dna" element={<FireDnaPage />} />
          <Route path="/fire-calendar" element={<FireMemoryPage />} />
          <Route path="/critical-periods" element={<Navigate to="/fire-memory" replace />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
          <Route path="/fire-events" element={<HarmonizedMapPage />} />
          <Route path="/methodology" element={<MethodologyPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/area" element={<AreaIntelligencePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </React.Suspense>
      </Router>
      </LanguageProvider>
    </AppProvider>
  </React.StrictMode>,
);
