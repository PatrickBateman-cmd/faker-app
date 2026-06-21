import { NavLink } from "react-router-dom";
import { ThemeSwitcher } from "../ThemeSwitcher/ThemeSwitcher";

const NAV_ITEMS = [
  { path: "/", label: "Dashboard", icon: "◉" },
  { path: "/templates", label: "Templates", icon: "◇" },
  { path: "/iso20022", label: "ISO 20022", icon: "◎" },
  { path: "/financial", label: "Financial", icon: "▲" },
  { path: "/kaggle", label: "Kaggle", icon: "⬡" },
  { path: "/generation", label: "Generation", icon: "◆" },
  { path: "/datasets", label: "Datasets", icon: "▣" },
];

export function Sidebar() {
  return (
    <aside className="w-56 bg-[var(--surface)] border-r border-[var(--border)] flex flex-col p-4">
      <div className="text-lg font-bold text-[var(--accent)] mb-6">Faker App</div>
      <nav className="flex-1 space-y-1">
        {NAV_ITEMS.map(item => (
          <NavLink key={item.path} to={item.path} end
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                isActive ? "bg-[var(--accent)] text-white" : "text-[var(--text)] hover:bg-[var(--elevated)]"
              }`
            }>
            <span>{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>
      <ThemeSwitcher />
    </aside>
  );
}
