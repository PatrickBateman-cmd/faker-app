import { useEffect, useState } from "react";

const THEMES = [
  { value: "theme-mocha", label: "Mocha" },
  { value: "theme-macchiato", label: "Macchiato" },
  { value: "theme-frappe", label: "Frappé" },
  { value: "theme-latte", label: "Latte" },
];

export function ThemeSwitcher() {
  const [theme, setTheme] = useState(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("theme") || "theme-mocha";
    }
    return "theme-mocha";
  });

  useEffect(() => {
    document.documentElement.className = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <div className="flex flex-col gap-1 mt-2 pt-2 border-t border-[var(--border)]">
      <label className="text-xs text-[var(--muted)] uppercase tracking-wider px-3">
        Theme
      </label>
      <select
        value={theme}
        onChange={(e) => setTheme(e.target.value)}
        className="mx-3 px-2 py-1.5 text-xs bg-[var(--elevated)] text-[var(--text)] border border-[var(--border)] rounded focus:outline-none"
      >
        {THEMES.map((t) => (
          <option key={t.value} value={t.value}>
            {t.label}
          </option>
        ))}
      </select>
    </div>
  );
}
