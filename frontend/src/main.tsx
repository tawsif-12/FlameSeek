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
import PipelineFreshness from "./components/PipelineFreshness";
import "./theme.css";
import "./responsive.css";

const PRIMARY_NAVIGATION = [
  { to: "/", label: "Home", end: true },
  { to: "/fire-map", label: "Fire Now" },
  { to: "/search", label: "Search" },
  { to: "/methodology", label: "Methodology" },
  { to: "/about", label: "About" },
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
const LocationDashboard = React.lazy(() => import('./pages/LocationDashboard'));

function LanguageToggle() {
  const { lang, setLang, t } = useLanguage();
  return (
    <button className="header-language" type="button" aria-label="Switch language English / Bangla" onClick={() => setLang(lang === "en" ? "bn" : "en")}>
      {t("toggle")}
    </button>
  );
}

function Header() {
  const [menuOpen, setMenuOpen] = React.useState(false);
  const headerRef = React.useRef<HTMLElement>(null);
  const location = useLocation();
  React.useEffect(() => {
    setMenuOpen(false);
  }, [location]);
  React.useEffect(() => {
    const outside = (event: PointerEvent) => {
      if (!headerRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, []);
  return (
    <header ref={headerRef} className="app-header mission-header" onKeyDown={(event) => { if (event.key === "Escape") setMenuOpen(false); }}>
      <Link to="/" className="brand-mark" style={{ textDecoration: "none" }}>
        <span className="brand-glyph brand-flame" aria-hidden="true">🔥</span>
        <div>
          <h1>FlameSeek</h1>
          <p className="eyebrow">Global Fire Intelligence</p>
        </div>
      </Link>
      <button type="button" className="mobile-menu-toggle" aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? "Close" : "Menu"}</button>
      <nav id="primary-navigation" className={`primary-navigation ${menuOpen ? "mobile-open" : ""}`} aria-label="Primary navigation" onClick={(event) => { if ((event.target as HTMLElement).closest("a")) setMenuOpen(false); }}>
        {PRIMARY_NAVIGATION.map((item) => (
          <NavLink key={item.to} to={item.to} end={"end" in item ? item.end : undefined}>
            {item.label}
          </NavLink>
        ))}
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
        <PipelineFreshness />
        <React.Suspense fallback={<main className="content-page" role="status">Loading page…</main>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/fire-map" element={<FireGlobePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/location" element={<LocationDashboard />} />
          <Route path="/location/:section" element={<LocationDashboard />} />
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
