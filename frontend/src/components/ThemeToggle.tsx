import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

type Theme = "day" | "night";

export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() =>
    document.documentElement.dataset.theme === "day" ? "day" : "night",
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("flameseek-theme", theme); } catch { /* Storage may be disabled. */ }
  }, [theme]);

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={`Switch to ${theme === "day" ? "night" : "day"} theme`}
      aria-pressed={theme === "day"}
      title={`Switch to ${theme === "day" ? "night" : "day"} theme`}
      onClick={() => setTheme(theme === "day" ? "night" : "day")}
    >
      {theme === "day" ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
      <span>{theme === "day" ? "Day" : "Night"}</span>
    </button>
  );
}
