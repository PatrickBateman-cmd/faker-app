import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { FinancialPanel } from "./components/FinancialPanel/FinancialPanel";
import { GenerationControls } from "./components/GenerationControls/GenerationControls";
import { Iso20022Panel } from "./components/Iso20022Panel/Iso20022Panel";
import { ResultsViewer } from "./components/ResultsViewer/ResultsViewer";
import { TemplateLibrary } from "./components/TemplateLibrary/TemplateLibrary";
import { ThemeSwitcher } from "./components/ThemeSwitcher/ThemeSwitcher";

type Page = "dashboard" | "templates" | "iso20022" | "generation" | "datasets" | "financial";

function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [pendingTemplate, setPendingTemplate] = useState<string | null>(null);

  const { data, isPending, error } = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Health check failed");
      return res.json();
    },
  });

  const navItems: { label: string; key: Page }[] = [
    { label: "Dashboard", key: "dashboard" },
    { label: "Templates", key: "templates" },
    { label: "ISO 20022", key: "iso20022" },
    { label: "Financial", key: "financial" },
    { label: "Generation", key: "generation" },
    { label: "Datasets", key: "datasets" },
  ];

  return (
    <div className="flex h-screen bg-[var(--bg)] text-[var(--text)]">
      <aside className="w-64 border-r border-[var(--border)] p-4 flex flex-col gap-2">
        <h1 className="text-lg font-bold text-[var(--accent)]">Faker App</h1>
        <nav className="flex flex-col gap-1 text-sm">
          {navItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setPage(item.key)}
              className={`text-left px-3 py-2 rounded transition-colors ${
                page === item.key
                  ? "bg-[var(--selection)] text-[var(--accent)]"
                  : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--elevated)]"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <ThemeSwitcher />
      </aside>
      <main className="flex-1 p-8 overflow-y-auto">
        {page === "dashboard" && (
          <>
            <h2 className="text-2xl font-semibold mb-4">Dashboard</h2>
            {isPending && <p className="text-[var(--muted)]">Connecting...</p>}
            {error && (
              <p className="text-[var(--red)]">
                Backend unreachable: {error.message}
              </p>
            )}
            {data && (
              <div className="space-y-2">
                <p className="text-[var(--green)]">Backend connected</p>
                <p className="text-sm text-[var(--muted)]">
                  Status: {data.status} | DuckDB: {data.duckdb} | v
                  {data.version}
                </p>
              </div>
            )}
          </>
        )}
        {page === "templates" && <TemplateLibrary onApply={(name) => { setPendingTemplate(name); setPage("generation"); }} />}
        {page === "iso20022" && <Iso20022Panel onApply={(name) => { setPendingTemplate(name); setPage("generation"); }} />}
        {page === "financial" && <FinancialPanel onNavigate={(p) => setPage(p as typeof page)} />}
        {page === "generation" && <GenerationControls onNavigate={(p) => setPage(p as typeof page)} pendingTemplate={pendingTemplate} />}
        {page === "datasets" && <ResultsViewer />}
      </main>
    </div>
  );
}

export default App;
