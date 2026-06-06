import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-4">
      <div className="text-sm text-[var(--muted)]">{label}</div>
      <div className="text-2xl font-bold text-[var(--accent)]">{value}</div>
    </div>
  );
}

export function Dashboard() {
  const navigate = useNavigate();

  const { data: info } = useQuery({
    queryKey: ["app-info"],
    queryFn: async () => {
      const res = await fetch("/api/info");
      if (!res.ok) throw new Error("Failed to fetch app info");
      return res.json();
    },
    refetchInterval: 30000,
  });

  return (
    <section className="p-6">
      <h1 className="text-2xl font-bold text-[var(--text)] mb-6">Dashboard</h1>

      <div className="grid grid-cols-4 gap-4 mb-8">
        <StatCard label="Datasets" value={info?.datasets?.toLocaleString() ?? "..."} />
        <StatCard label="Total Rows" value={info?.total_rows?.toLocaleString() ?? "..."} />
        <StatCard label="Templates" value={info?.templates?.toLocaleString() ?? "..."} />
        <StatCard label="Runs" value={info?.runs?.toLocaleString() ?? "..."} />
      </div>

      <div className="flex gap-4 mb-8">
        <button onClick={() => navigate("/generation")} className="px-4 py-2 bg-[var(--accent)] hover:bg-[var(--accent)] text-white text-sm rounded transition-colors">
          New Generation
        </button>
        <button onClick={() => navigate("/templates")} className="px-4 py-2 bg-[var(--surface)] border border-[var(--border)] hover:bg-[var(--elevated)] text-[var(--text)] text-sm rounded transition-colors">
          Browse Templates
        </button>
        <button onClick={() => navigate("/financial")} className="px-4 py-2 bg-[var(--surface)] border border-[var(--border)] hover:bg-[var(--elevated)] text-[var(--text)] text-sm rounded transition-colors">
          Financial Data
        </button>
      </div>

      <h2 className="text-lg font-semibold text-[var(--text)] mb-3">Recent Datasets</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="text-left py-2 pr-4 text-[var(--muted)] font-medium">Name</th>
            <th className="text-left py-2 pr-4 text-[var(--muted)] font-medium">Rows</th>
            <th className="text-left py-2 text-[var(--muted)] font-medium">Created</th>
          </tr>
        </thead>
        <tbody>
          {info?.recent_datasets?.map((ds: any) => (
            <tr key={ds.name} className="border-b border-[var(--border)]">
              <td className="py-2 pr-4 text-[var(--text)]">{ds.name}</td>
              <td className="py-2 pr-4 text-[var(--text)]">{ds.rows}</td>
              <td className="py-2 text-[var(--muted)]">{ds.created_at?.slice(0, 19)}</td>
            </tr>
          ))}
          {(!info?.recent_datasets || info.recent_datasets.length === 0) && (
            <tr>
              <td colSpan={3} className="py-4 text-[var(--muted)] text-center">No datasets yet</td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
