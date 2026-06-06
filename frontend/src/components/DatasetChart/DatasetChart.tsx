import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { fetchDatasetRows, fetchDatasetColumns } from "../../api/datasets";

interface DatasetChartProps {
  datasetId: string;
}

type ChartType = "bar" | "line" | "pie";

const COLORS = ["#6366f1", "#ec4899", "#f59e0b", "#10b981", "#3b82f6", "#8b5cf6", "#ef4444", "#14b8a6"];

export function DatasetChart({ datasetId }: DatasetChartProps) {
  const [chartType, setChartType] = useState<ChartType>("bar");
  const [xAxis, setXAxis] = useState<string>("");
  const [yAxis, setYAxis] = useState<string>("");

  const { data: rowsData } = useQuery({
    queryKey: ["dataset-rows", datasetId],
    queryFn: () => fetchDatasetRows(datasetId, 1, 100),
  });

  const { data: columns } = useQuery({
    queryKey: ["dataset-columns", datasetId],
    queryFn: () => fetchDatasetColumns(datasetId),
  });

  const numericColumns = (columns || []).filter((c: any) =>
    ["BIGINT", "DOUBLE", "INTEGER", "FLOAT", "DECIMAL"].includes(c.type)
  );
  const categoricalColumns = (columns || []).filter((c: any) =>
    ["VARCHAR", "STRING"].includes(c.type)
  );

  const rows = rowsData?.rows || [];
  const total = rowsData?.total || 0;

  if (!xAxis && categoricalColumns.length > 0) setXAxis(categoricalColumns[0].name);
  if (!yAxis && numericColumns.length > 0) setYAxis(numericColumns[0].name);

  const renderChart = () => {
    if (!xAxis || !yAxis || rows.length === 0) {
      return <div className="text-[var(--muted)] p-8 text-center">Select X and Y axes to view chart</div>;
    }

    const chartData = rows.map((r: any) => ({ ...r }));

    switch (chartType) {
      case "bar":
        return (
          <ResponsiveContainer width="100%" height={400}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey={xAxis} tick={{ fill: "var(--muted)" }} />
              <YAxis tick={{ fill: "var(--muted)" }} />
              <Tooltip />
              <Legend />
              <Bar dataKey={yAxis} fill="var(--accent)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        );
      case "line":
        return (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey={xAxis} tick={{ fill: "var(--muted)" }} />
              <YAxis tick={{ fill: "var(--muted)" }} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey={yAxis} stroke="var(--accent)" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        );
      case "pie":
        return (
          <ResponsiveContainer width="100%" height={400}>
            <PieChart>
              <Pie data={chartData} dataKey={yAxis} nameKey={xAxis} cx="50%" cy="50%" outerRadius={150} label>
                {chartData.map((_: any, i: number) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        );
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label className="block text-sm text-[var(--muted)] mb-1">Chart Type</label>
          <div className="flex gap-2">
            {(["bar", "line", "pie"] as ChartType[]).map(t => (
              <button key={t} onClick={() => setChartType(t)}
                className={`px-3 py-1 rounded text-sm ${chartType === t ? "bg-[var(--accent)] text-white" : "bg-[var(--surface)] text-[var(--text)] border border-[var(--border)]"}`}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-sm text-[var(--muted)] mb-1">X Axis</label>
          <select value={xAxis} onChange={e => setXAxis(e.target.value)}
            className="bg-[var(--surface)] text-[var(--text)] border border-[var(--border)] rounded px-3 py-1">
            <option value="">-- Select --</option>
            {[...categoricalColumns, ...numericColumns].map((c: any) => (
              <option key={c.name} value={c.name}>{c.name} ({c.type})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm text-[var(--muted)] mb-1">Y Axis</label>
          <select value={yAxis} onChange={e => setYAxis(e.target.value)}
            className="bg-[var(--surface)] text-[var(--text)] border border-[var(--border)] rounded px-3 py-1">
            <option value="">-- Select --</option>
            {numericColumns.map((c: any) => (
              <option key={c.name} value={c.name}>{c.name} ({c.type})</option>
            ))}
          </select>
        </div>
      </div>

      <div className="bg-[var(--surface)] rounded-lg border border-[var(--border)] p-4">
        {renderChart()}
      </div>
    </div>
  );
}
