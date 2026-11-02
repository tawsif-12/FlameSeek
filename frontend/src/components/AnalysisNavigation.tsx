import { NavLink, useNavigate } from "react-router-dom";

const ANALYSIS_PAGES = [
  { to: "/fire-memory", label: "Fire Memory" },
  { to: "/fire-dna", label: "Fire DNA" },
  { to: "/fire-calendar", label: "Burning Calendar" },
] as const;

export default function AnalysisNavigation() {
  const navigate = useNavigate();

  return (
    <nav className="analysis-navigation" aria-label="Fire history sections">
      <button type="button" className="analysis-back" onClick={() => navigate(-1)} aria-label="Go back to the previous page">
        <span aria-hidden="true">←</span> Back
      </button>
      <div className="analysis-navigation-links">
        {ANALYSIS_PAGES.map((page) => (
          <NavLink key={page.to} to={page.to} end>
            {page.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
