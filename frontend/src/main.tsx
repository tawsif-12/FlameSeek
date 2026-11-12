import React from "react";
import ReactDOM from "react-dom/client";
import { Link, NavLink, Navigate, Route, BrowserRouter as Router, Routes, useLocation } from "react-router-dom";
import "./styles.css";
import { AppProvider } from "./context/AppContext";
import { LanguageProvider } from "./context/LanguageContext";
import ThemeToggle from "./components/ThemeToggle";
import RouteLoadingFallback from "./components/RouteLoadingFallback";
import "./theme.css";
import "./responsive.css";

const PRIMARY_NAVIGATION = [
  { to: "/", label: "Home", end: true },
  { to: "/fire-map", label: "Fire Now" },
  { to: "/search", label: "Search" },
  { to: "/data-sources", label: "Data Sources" },
  { to: "/methodology", label: "Methodology" },
] as const;

// Keep every route out of the startup graph. The same stable loaders power
// navigation-intent prefetching; the browser deduplicates module requests.
const routeLoaders = {
  "/": () => import("./pages/HomePage"),
  "/fire-map": () => import("./pages/FireGlobePage"),
  "/search": () => import("./pages/SearchPage"),
  "/methodology": () => import("./pages/MethodologyPage"),
  "/fire-memory": () => import("./pages/FireMemoryPage"),
  "/fire-dna": () => import("./pages/FireDnaPage"),
  "/data-sources": () => import("./pages/DataSourcesPage"),
  "/fire-events": () => import("./pages/HarmonizedMapPage"),
  "/area": () => import("./pages/AreaIntelligencePage"),
} as const;
type PrefetchableRoute = keyof typeof routeLoaders;
const prefetchRoute = (route: string) => {
  const loader = routeLoaders[route as PrefetchableRoute];
  if (loader) void loader();
};

const LocationDashboard = React.lazy(() => import("./pages/LocationDashboard"));
const HomePage = React.lazy(routeLoaders["/"]);
const DataSourcesPage = React.lazy(routeLoaders["/data-sources"]);
const FireGlobePage = React.lazy(routeLoaders["/fire-map"]);
const FireMemoryPage = React.lazy(routeLoaders["/fire-memory"]);
const FireDnaPage = React.lazy(routeLoaders["/fire-dna"]);
const SearchPage = React.lazy(routeLoaders["/search"]);
const MethodologyPage = React.lazy(routeLoaders["/methodology"]);
const AreaIntelligencePage = React.lazy(routeLoaders["/area"]);

function MergedFeatureRedirect({ to, view }: { to: string; view?: string }) {
  const route = useLocation();
  const params = new URLSearchParams(route.search);
  if (view) params.set('view', view);
  return <Navigate replace to={`${to}${params.size ? `?${params}` : ''}${route.hash}`} />;
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
  React.useEffect(() => {
    // Warm small primary routes after first paint. The 3D globe is intentionally
    // fetched only on hover/focus so mobile users do not pay for it speculatively.
    const warm = () => ["/search", "/data-sources", "/methodology"].forEach(prefetchRoute);
    const win = window as typeof window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number; cancelIdleCallback?: (id: number) => void };
    if (win.requestIdleCallback) {
      const id = win.requestIdleCallback(warm, { timeout: 2500 });
      return () => win.cancelIdleCallback?.(id);
    }
    const id = window.setTimeout(warm, 1500);
    return () => window.clearTimeout(id);
  }, []);
  return (
    <header ref={headerRef} className="app-header mission-header" onKeyDown={(event) => { if (event.key === "Escape") setMenuOpen(false); }}>
      <Link to="/" className="brand-mark" style={{ textDecoration: "none" }}>
        <img className="brand-logo" src="/branding/flameseek-logo.png?v=3" width="52" height="52" alt="" />
        <div>
          <h1>FlameSeek</h1>
          <p className="eyebrow">Global Fire Intelligence</p>
        </div>
      </Link>
      <button type="button" className="mobile-menu-toggle" aria-expanded={menuOpen} aria-controls="primary-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? "Close" : "Menu"}</button>
      <nav id="primary-navigation" className={`primary-navigation ${menuOpen ? "mobile-open" : ""}`} aria-label="Primary navigation" onClick={(event) => { if ((event.target as HTMLElement).closest("a")) setMenuOpen(false); }}>
        {PRIMARY_NAVIGATION.map((item) => (
          <NavLink key={item.to} to={item.to} end={"end" in item ? item.end : undefined}
            onPointerEnter={() => prefetchRoute(item.to)} onFocus={() => prefetchRoute(item.to)} onTouchStart={() => prefetchRoute(item.to)}>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <div className="header-actions">
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
        <React.Suspense fallback={<RouteLoadingFallback />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/fire-map" element={<FireGlobePage />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/location" element={<LocationDashboard />} />
          <Route path="/location/:section" element={<LocationDashboard />} />
          <Route path="/fire-memory" element={<MergedFeatureRedirect to="/fire-calendar" />} />
          <Route path="/fire-dna" element={<FireDnaPage />} />
          <Route path="/fire-calendar" element={<FireMemoryPage />} />
          <Route path="/critical-periods" element={<MergedFeatureRedirect to="/fire-calendar" />} />
          <Route path="/data-sources" element={<DataSourcesPage />} />
          <Route path="/fire-events" element={<MergedFeatureRedirect to="/area" view="events" />} />
          <Route path="/methodology" element={<MethodologyPage />} />
          <Route path="/about" element={<Navigate to="/data-sources" replace />} />
          <Route path="/area" element={<AreaIntelligencePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </React.Suspense>
      </Router>
      </LanguageProvider>
    </AppProvider>
  </React.StrictMode>,
);
