import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createTemplate, fetchTemplate, fetchTemplates } from "../../api/templates";
import type { Template } from "../../types/template";

export function TemplateLibrary({ onApply }: { onApply?: (name: string) => void }) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [xmlInput, setXmlInput] = useState("");

  const list = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });

  const detail = useQuery({
    queryKey: ["template", selected],
    queryFn: () => fetchTemplate(selected!),
    enabled: !!selected,
  });

  const createMut = useMutation({
    mutationFn: createTemplate,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setShowUpload(false);
      setXmlInput("");
    },
  });

  function handleUpload() {
    createMut.mutate(xmlInput);
  }

  return (
    <div className="flex gap-6 h-full">
      <div className="w-72 shrink-0 flex flex-col gap-2">
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider">
            Templates
          </h3>
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="text-xs text-[var(--accent)] hover:text-[var(--accent)]"
          >
            + New
          </button>
        </div>

        {list.isPending && <p className="text-sm text-[var(--muted)]">Loading...</p>}
        {list.error && (
          <p className="text-sm text-[var(--red)]">{list.error.message}</p>
        )}

        <div className="flex flex-col gap-1 overflow-y-auto">
          {(list.data ?? []).map((t) => (
            <div
              key={t.name}
              onClick={() => setSelected(t.name)}
              className={`flex items-center justify-between px-3 py-2 rounded cursor-pointer text-sm transition-colors ${
                selected === t.name
                  ? "bg-[var(--selection)] text-[var(--accent)] border border-[var(--accent)]"
                  : "text-[var(--muted)] hover:bg-[var(--elevated)] border border-transparent"
              }`}
            >
              <div className="min-w-0">
                <div className="truncate">{t.name}</div>
                <div className="text-xs text-[var(--muted)]">{t.category}</div>
              </div>
              <span className="text-xs text-[var(--muted)] shrink-0 ml-2">
                {t.field_count}
              </span>
            </div>
          ))}
        </div>

        {showUpload && (
          <div className="mt-2 flex flex-col gap-2">
            <textarea
              value={xmlInput}
              onChange={(e) => setXmlInput(e.target.value)}
              placeholder="Paste XML template content..."
              rows={6}
              className="bg-[var(--surface)] border border-[var(--border)] rounded px-2 py-1 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
            />
            <div className="flex gap-2">
              <button
                onClick={handleUpload}
                disabled={!xmlInput.trim() || createMut.isPending}
                className="px-3 py-1 text-xs bg-[var(--accent)] hover:bg-[var(--accent)] disabled:bg-[var(--elevated)] disabled:text-[var(--muted)] rounded transition-colors"
              >
                {createMut.isPending ? "Saving..." : "Save"}
              </button>
              <button
                onClick={() => setShowUpload(false)}
                className="px-3 py-1 text-xs text-[var(--muted)] hover:text-[var(--text)]"
              >
                Cancel
              </button>
            </div>
            {createMut.isError && (
              <p className="text-xs text-[var(--red)]">{createMut.error.message}</p>
            )}
          </div>
        )}
      </div>

      <div className="flex-1 min-w-0">
        {detail.isPending && (
          <p className="text-sm text-[var(--muted)]">Loading template...</p>
        )}
        {detail.data && <TemplateDetail template={detail.data} onApply={onApply} />}
        {!detail.isPending && !detail.data && !selected && (
          <p className="text-sm text-[var(--muted)]">Select a template to view</p>
        )}
        {detail.isError && (
          <p className="text-sm text-[var(--red)]">{detail.error.message}</p>
        )}
      </div>
    </div>
  );
}

function TemplateDetail({ template, onApply }: { template: Template; onApply?: (name: string) => void }) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-semibold text-[var(--text)]">
            {template.name}
          </h2>
          <p className="text-sm text-[var(--muted)]">{template.meta.description}</p>
          <div className="flex gap-3 mt-1 text-xs text-[var(--muted)]">
            <span>v{template.meta.version}</span>
            <span>{template.category}</span>
            <span>{template.fields.length} fields</span>
          </div>
        </div>
        <button
          onClick={() => onApply?.(template.name)}
          className="px-4 py-1.5 text-sm bg-[var(--accent)] hover:bg-[var(--accent)] rounded transition-colors"
        >
          Apply
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[var(--muted)] border-b border-[var(--border)]">
              <th className="pb-2 pr-4 font-medium">Field</th>
              <th className="pb-2 pr-4 font-medium">Type</th>
              <th className="pb-2 pr-4 font-medium">Generator</th>
              <th className="pb-2 pr-4 font-medium">Unique</th>
              <th className="pb-2 font-medium">Constraints</th>
            </tr>
          </thead>
          <tbody className="text-[var(--text)]">
            {template.fields.map((f) => (
              <tr key={f.name} className="border-b border-[var(--border)]">
                <td className="py-2 pr-4">{f.name}</td>
                <td className="py-2 pr-4 text-[var(--muted)]">{f.type}</td>
                <td className="py-2 pr-4 text-[var(--accent)]">{f.generator}</td>
                <td className="py-2 pr-4">{f.unique ? "Yes" : "No"}</td>
                <td className="py-2 text-[var(--muted)] max-w-xs truncate">
                  {f.constraint
                    ? Object.entries(f.constraint)
                        .filter(
                          ([, v]) => v !== null && v !== undefined && v !== "",
                        )
                        .map(([k, v]) => `${k}=${v}`)
                        .join(", ")
                    : "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {template.relationships.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-[var(--muted)] mb-2">
            Relationships
          </h4>
          <div className="flex flex-col gap-1">
            {template.relationships.map((r, i) => (
              <div
                key={i}
                className="text-sm text-[var(--muted)] bg-[var(--surface)] rounded px-3 py-1.5"
              >
                {r.type}: {r.source}
                {r.target ? ` → ${r.target}` : ""}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
