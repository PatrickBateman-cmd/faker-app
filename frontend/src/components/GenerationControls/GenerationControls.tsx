import { DndContext, closestCenter } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchTemplate, fetchTemplates, generateDatasets } from "../../api/generation";
import { GenerationResults } from "../ResultsViewer/ResultsViewer";
import { CollapsibleSection } from "../CollapsibleSection/CollapsibleSection";
import type {
  DatasetDefinition,
  DatasetResult,
  FieldBreakConfig,
  FieldDef,
  TemplateSummary,
} from "../../types/generation";

const BREAK_STYLE_OPTIONS: FieldBreakConfig["break_style"][] = ["drift", "different", "null"];

function emptyFieldBreak(fieldName: string): FieldBreakConfig {
  return { field_name: fieldName, break_rate: 10, break_style: "drift", drift_pct: 2 };
}

const GENERATOR_OPTIONS = [
  "first_name", "last_name", "name", "email", "phone_number",
  "job", "company", "catch_phrase", "domain_name", "url",
  "country", "country_code", "city", "street_address", "zipcode",
  "text", "boolean", "random_int", "pydecimal", "uuid4", "uuid_int",
  "bothify", "random_element", "currency_code", "swift", "iban", "bban",
  "date_between", "date_of_birth", "date_time", "word",
];

const TYPE_OPTIONS = ["string", "integer", "float", "boolean", "date"];

const GENERATOR_OPTIONS_LIST = GENERATOR_OPTIONS;
const TYPE_OPTIONS_LIST = TYPE_OPTIONS;

function SortableFieldRow({
  field, index, dsIndex, onChange, onRemove
}: {
  field: FieldDef;
  index: number;
  dsIndex: number;
  onChange: (dsIndex: number, fieldIndex: number, updater: (f: FieldDef) => FieldDef) => void;
  onRemove: (dsIndex: number, fieldIndex: number) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: `field-${dsIndex}-${index}` });
  const style = { transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 };

  return (
    <div ref={setNodeRef} style={style} className="flex items-center gap-1 text-xs">
      <button {...attributes} {...listeners} className="cursor-grab text-[var(--muted)] px-1">⠿</button>
      <input
        value={field.name}
        onChange={(e) => onChange(dsIndex, index, (f) => ({ ...f, name: e.target.value }))}
        className="w-24 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
        placeholder="field_name"
      />
      <select
        value={field.generator}
        onChange={(e) => onChange(dsIndex, index, (f) => ({ ...f, generator: e.target.value }))}
        className="w-28 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)] focus:outline-none focus:border-cyan-700"
      >
        {GENERATOR_OPTIONS_LIST.map((g) => (
          <option key={g} value={g}>{g}</option>
        ))}
      </select>
      <select
        value={field.type}
        onChange={(e) => onChange(dsIndex, index, (f) => ({ ...f, type: e.target.value }))}
        className="w-18 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--muted)]"
      >
        {TYPE_OPTIONS_LIST.map((t) => (
          <option key={t} value={t}>{t}</option>
        ))}
      </select>
      <button
        onClick={() => onRemove(dsIndex, index)}
        className="text-[var(--muted)] hover:text-[var(--red)] px-1"
        title="Remove field"
      >
        x
      </button>
    </div>
  );
}

function emptyField(): FieldDef {
  return { name: "", generator: "text", type: "string", unique: false };
}

export function GenerationControls({ onNavigate, pendingTemplate: externalTemplate }: { onNavigate?: (page: string) => void; pendingTemplate?: string | null }) {
  const [datasetCount, setDatasetCount] = useState(1);
  const [datasets, setDatasets] = useState<DatasetDefinition[]>([emptyDataset("Dataset 1")]);
  const [homogeneity, setHomogeneity] = useState(50);
  const [seed, setSeed] = useState("");
  const [overlapRatio, setOverlapRatio] = useState(0);
  const [exactFields, setExactFields] = useState("");
  const [reconciliationMode, setReconciliationMode] = useState(false);
  const [fieldBreaks, setFieldBreaks] = useState<FieldBreakConfig[]>([]);
  const [mode, setMode] = useState<"flat" | "grouped">("flat");
  const [results, setResults] = useState<DatasetResult[] | null>(null);
  const [overlapPoolSize, setOverlapPoolSize] = useState<number>(0);
  const [resultExactFields, setResultExactFields] = useState<string[]>([]);
  const [resultBreakCount, setResultBreakCount] = useState<number>(0);
  const [collapsedDatasets, setCollapsedDatasets] = useState<Set<number>>(new Set());

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });

  const generateMut = useMutation({
    mutationFn: generateDatasets,
    onSuccess: (data) => {
      setResults(data.datasets);
      setOverlapPoolSize(data.overlap_pool_size);
      setResultExactFields(data.exact_fields);
      setResultBreakCount(data.break_count ?? 0);
    },
  });

  function emptyDataset(name?: string): DatasetDefinition {
    return {
      name: name || "",
      rows: 100,
      fields: [emptyField()],
    };
  }

  function switchMode(newMode: "flat" | "grouped") {
    setMode(newMode);
    setDatasets((prev) =>
      prev.map((d) => {
        if (newMode === "grouped" && !d.group_config) {
          return {
            ...d,
            group_config: {
              num_groups: 4,
              split_pct: 100,
              parent_fields: d.fields.length > 0 ? d.fields : [emptyField()],
              child_fields: [emptyField()],
            },
          };
        }
        if (newMode === "flat") {
          const { group_config, ...rest } = d;
          return rest;
        }
        return d;
      })
    );
    setResults(null);
  }

  function handleDatasetCountChange(count: number) {
    const c = Math.max(1, Math.min(4, count));
    setDatasetCount(c);
    setDatasets((prev) => {
      const updated = [...prev];
      while (updated.length < c) {
        updated.push(emptyDataset(`Dataset ${updated.length + 1}`));
      }
      return updated.slice(0, c);
    });
  }

  function updateDataset(index: number, updater: (d: DatasetDefinition) => DatasetDefinition) {
    setDatasets((prev) => {
      const updated = [...prev];
      updated[index] = updater(updated[index]);
      return updated;
    });
    setResults(null);
  }

  function addField(dsIndex: number) {
    updateDataset(dsIndex, (d) => ({
      ...d,
      fields: [...d.fields, emptyField()],
    }));
  }

  function removeField(dsIndex: number, fieldIndex: number) {
    updateDataset(dsIndex, (d) => ({
      ...d,
      fields: d.fields.filter((_, i) => i !== fieldIndex),
    }));
  }

  function moveField(dsIndex: number, oldIndex: number, newIndex: number) {
    updateDataset(dsIndex, (d) => ({
      ...d,
      fields: arrayMove(d.fields, oldIndex, newIndex),
    }));
  }

  function toggleDatasetCollapsed(dsIndex: number) {
    setCollapsedDatasets((prev) => {
      const next = new Set(prev);
      if (next.has(dsIndex)) next.delete(dsIndex);
      else next.add(dsIndex);
      return next;
    });
  }

  function moveDataset(oldIndex: number, newIndex: number) {
    setDatasets((prev) => arrayMove(prev, oldIndex, newIndex));
    setResults(null);
  }

  function updateField(dsIndex: number, fieldIndex: number, updater: (f: FieldDef) => FieldDef) {
    updateDataset(dsIndex, (d) => ({
      ...d,
      fields: d.fields.map((f, i) => (i === fieldIndex ? updater(f) : f)),
    }));
  }

  function _mapTemplateFields(t: { fields: any[] }) {
    return t.fields.map((f) => ({
      name: f.name,
      generator: f.generator,
      type: f.type,
      unique: f.unique,
      formula: f.formula,
      constraint: f.constraint || null,
    }));
  }

  function applyTemplate(dsIndex: number, templateName: string) {
    fetchTemplate(templateName).then((t) => {
      const mapped = _mapTemplateFields(t);
      updateDataset(dsIndex, (d) => ({
        ...d,
        name: t.name,
        template: t.name,
        fields: mapped,
        group_config: d.group_config
          ? { ...d.group_config, parent_fields: mapped, child_fields: [] }
          : d.group_config,
      }));
    });
  }

  useEffect(() => {
    if (externalTemplate) {
      applyTemplate(0, externalTemplate);
    }
  }, [externalTemplate]);

  function toggleReconciliationMode(checked: boolean) {
    setReconciliationMode(checked);
    if (checked) {
      setOverlapRatio(100);
    } else {
      setFieldBreaks([]);
    }
    setResults(null);
  }

  // Fields actually eligible for exact_fields/field_breaks on a dataset: for grouped
  // datasets the backend only supports child-level fields (parent fields repeat once
  // per group, so per-row pool injection doesn't apply to them); for flat datasets
  // any field qualifies.
  function eligibleFieldNames(ds: DatasetDefinition | undefined): string[] {
    if (!ds) return [];
    const source = ds.group_config ? ds.group_config.child_fields : ds.fields;
    return source.map((f) => f.name).filter(Boolean);
  }

  function addFieldBreak() {
    const joinKey = exactFields.split(",").map((s) => s.trim()).filter(Boolean)[0];
    const candidate = eligibleFieldNames(datasets[0])
      .find((f) => f !== joinKey && !fieldBreaks.some((fb) => fb.field_name === f));
    if (candidate && !exactFields.split(",").map((s) => s.trim()).includes(candidate)) {
      setExactFields((prev) => (prev.trim() ? `${prev}, ${candidate}` : candidate));
    }
    setFieldBreaks((prev) => [...prev, emptyFieldBreak(candidate ?? "")]);
  }

  function updateFieldBreak(index: number, updater: (fb: FieldBreakConfig) => FieldBreakConfig) {
    setFieldBreaks((prev) => prev.map((fb, i) => (i === index ? updater(fb) : fb)));
  }

  function removeFieldBreak(index: number) {
    setFieldBreaks((prev) => prev.filter((_, i) => i !== index));
  }

  function handleGenerate() {
    const seedVal = seed ? parseInt(seed, 10) : undefined;
    const parsedExactFields = exactFields
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    generateMut.mutate({
      datasets: datasets.map((d) => ({
        ...d,
        rows: d.rows || 100,
      })),
      homogeneity,
      seed: seedVal && !isNaN(seedVal) ? seedVal : undefined,
      overlap_ratio: overlapRatio / 100,
      exact_fields: parsedExactFields,
      ...(reconciliationMode
        ? {
            reconciliation_mode: true,
            field_breaks: fieldBreaks
              .filter((fb) => fb.field_name)
              .map((fb) => ({
                ...fb,
                break_rate: fb.break_rate / 100,
                drift_pct: fb.drift_pct / 100,
              })),
          }
        : {}),
    });
  }

  return (
    <div className="flex flex-col gap-6 h-full">
      <div className="flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-2">
          <label className="text-sm text-[var(--muted)]">Datasets:</label>
          <div className="flex gap-1">
            {[1, 2, 3, 4].map((n) => (
              <button
                key={n}
                onClick={() => handleDatasetCountChange(n)}
                className={`w-8 h-8 rounded text-sm transition-colors ${
                  datasetCount === n
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--elevated)] text-[var(--muted)] hover:bg-[var(--elevated)]"
                }`}
              >
                {n}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm text-[var(--muted)]">Homogeneity:</label>
          <input
            type="range"
            min={1}
            max={100}
            value={homogeneity}
            onChange={(e) => setHomogeneity(Number(e.target.value))}
            className="w-28"
          />
          <span className="text-sm text-[var(--accent)] w-10">{homogeneity}%</span>
        </div>

        <div className="flex items-center gap-2">
          <label className="text-sm text-[var(--muted)]">Seed:</label>
          <input
            type="number"
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            placeholder="random"
            className="w-24 bg-[var(--surface)] border border-[var(--border)] rounded px-2 py-1 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
          />
        </div>

        <div className="flex items-center gap-2">
          <label className={`text-sm ${reconciliationMode ? "text-[var(--muted)]/50" : "text-[var(--muted)]"}`}>Overlap:</label>
          <input
            type="range"
            min={0}
            max={100}
            value={overlapRatio}
            disabled={reconciliationMode}
            onChange={(e) => setOverlapRatio(Number(e.target.value))}
            className="w-28 disabled:opacity-50"
          />
          <span className="text-sm text-[var(--accent)] w-10">{overlapRatio}%</span>
        </div>

        <label className="flex items-center gap-2 text-sm text-[var(--text)] cursor-pointer">
          <input
            type="checkbox"
            checked={reconciliationMode}
            onChange={(e) => toggleReconciliationMode(e.target.checked)}
            className="accent-[var(--accent)]"
          />
          Reconciliation Mode
        </label>

        {(overlapRatio > 0 || reconciliationMode) && (
          <div className="flex items-center gap-2">
            <label className="text-sm text-[var(--muted)]">
              {reconciliationMode ? "Exact fields (first = join key):" : "Exact fields:"}
            </label>
            <input
              type="text"
              value={exactFields}
              onChange={(e) => setExactFields(e.target.value)}
              placeholder="e.g. trade_id, amount"
              className="w-48 bg-[var(--surface)] border border-[var(--border)] rounded px-2 py-1 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
            />
            {mode === "grouped" && (
              <span className="text-xs text-[var(--muted)]">
                Grouped datasets: must be a child field, not a parent field.
              </span>
            )}
          </div>
        )}
      </div>

      {mode === "grouped" && (overlapRatio > 0 || reconciliationMode) && (() => {
        const parentNames = new Set(
          (datasets[0]?.group_config?.parent_fields ?? []).map((f) => f.name)
        );
        const invalid = exactFields
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .filter((f) => parentNames.has(f));
        return invalid.length > 0 ? (
          <p className="text-xs text-[var(--red)]">
            {invalid.map((f) => `"${f}"`).join(", ")} {invalid.length === 1 ? "is a parent field" : "are parent fields"} — move{" "}
            {invalid.length === 1 ? "it" : "them"} to Child Fields to use for exact fields / breaks.
          </p>
        ) : null;
      })()}

      {reconciliationMode && (
        <div className="flex flex-col gap-2 bg-[var(--surface)] border border-[var(--border)] rounded p-3">
          <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-wider">Field Breaks</p>
          {eligibleFieldNames(datasets[0]).length === 0 ? (
            <p className="text-xs text-[var(--red)]">
              {mode === "grouped"
                ? "No child fields yet — move at least one field from Parent Fields to Child Fields to add a break rule."
                : "Add at least one field to the first dataset to add a break rule."}
            </p>
          ) : !exactFields.split(",").map((s) => s.trim()).filter(Boolean)[0] ? (
            <p className="text-xs text-[var(--red)]">
              Set a join key in Exact Fields above before adding break rules.
            </p>
          ) : fieldBreaks.length === 0 ? (
            <p className="text-xs text-[var(--muted)]">No break rules — datasets will match exactly on the fields above.</p>
          ) : null}
          {fieldBreaks.map((fb, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <select
                value={fb.field_name}
                onChange={(e) => {
                  const name = e.target.value;
                  updateFieldBreak(i, (f) => ({ ...f, field_name: name }));
                  if (name && !exactFields.split(",").map((s) => s.trim()).includes(name)) {
                    setExactFields((prev) => (prev.trim() ? `${prev}, ${name}` : name));
                  }
                }}
                className="w-32 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)]"
              >
                <option value="" disabled>field…</option>
                {eligibleFieldNames(datasets[0])
                  .filter((f) => f !== exactFields.split(",").map((s) => s.trim()).filter(Boolean)[0])
                  .map((f) => (
                    <option key={f} value={f}>{f}</option>
                  ))}
              </select>
              <label className="text-[var(--muted)]">Rate:</label>
              <input
                type="range"
                min={0}
                max={100}
                value={fb.break_rate}
                onChange={(e) => updateFieldBreak(i, (f) => ({ ...f, break_rate: Number(e.target.value) }))}
                className="w-20"
              />
              <span className="text-[var(--accent)] w-9">{fb.break_rate}%</span>
              <select
                value={fb.break_style}
                onChange={(e) => updateFieldBreak(i, (f) => ({ ...f, break_style: e.target.value as FieldBreakConfig["break_style"] }))}
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)]"
              >
                {BREAK_STYLE_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              {fb.break_style === "drift" && (
                <>
                  <label className="text-[var(--muted)]">Drift:</label>
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={fb.drift_pct}
                    onChange={(e) => updateFieldBreak(i, (f) => ({ ...f, drift_pct: Math.max(1, Number(e.target.value) || 1) }))}
                    className="w-14 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)]"
                  />
                  <span className="text-[var(--muted)]">%</span>
                </>
              )}
              <button
                onClick={() => removeFieldBreak(i)}
                className="text-[var(--muted)] hover:text-[var(--red)] px-1"
                title="Remove break rule"
              >
                x
              </button>
            </div>
          ))}
          <button
            onClick={addFieldBreak}
            disabled={
              eligibleFieldNames(datasets[0]).length === 0 ||
              !exactFields.split(",").map((s) => s.trim()).filter(Boolean)[0]
            }
            className="self-start text-xs text-[var(--muted)] hover:text-[var(--text)] disabled:opacity-40 disabled:cursor-not-allowed"
          >
            + Add break rule
          </button>
        </div>
      )}

      {/* Flat / Grouped toggle */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 text-sm text-[var(--text)] cursor-pointer">
          <input
            type="radio"
            name="genMode"
            checked={mode === "flat"}
            onChange={() => switchMode("flat")}
            className="accent-[var(--accent)]"
          />
          Flat
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--text)] cursor-pointer">
          <input
            type="radio"
            name="genMode"
            checked={mode === "grouped"}
            onChange={() => switchMode("grouped")}
            className="accent-[var(--accent)]"
          />
          Parent-Child
        </label>
      </div>

      <DndContext collisionDetection={closestCenter} onDragEnd={(e) => {
        const { active, over } = e;
        if (over && active.id !== over.id) {
          const oldIndex = parseInt(active.id.toString().split("-")[1]);
          const newIndex = parseInt(over.id.toString().split("-")[1]);
          moveDataset(oldIndex, newIndex);
        }
      }}>
      <SortableContext items={datasets.map((_, i) => `dataset-${i}`)} strategy={verticalListSortingStrategy}>
      <div className="flex gap-4 flex-1 min-h-0 overflow-auto items-start">
        {datasets.map((ds, dsIndex) => (
          <CollapsibleSection
            key={dsIndex}
            id={`dataset-${dsIndex}`}
            title={ds.name || `Dataset ${dsIndex + 1}`}
            collapsed={collapsedDatasets.has(dsIndex)}
            onToggleCollapse={() => toggleDatasetCollapsed(dsIndex)}
            className="flex-1 min-w-0"
          >
            <div className="flex items-center justify-between">
              <input
                value={ds.name}
                onChange={(e) =>
                  updateDataset(dsIndex, (d) => ({ ...d, name: e.target.value }))
                }
                className="bg-transparent border-b border-[var(--border)] px-1 py-0.5 text-sm font-semibold text-[var(--text)] focus:outline-none focus:border-cyan-700"
                placeholder="Dataset name"
              />
              <select
                onChange={(e) => e.target.value && applyTemplate(dsIndex, e.target.value)}
                value=""
                className="bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1 text-xs text-[var(--muted)]"
              >
                <option value="" disabled>Load template</option>
                {(templates.data ?? []).map((t: TemplateSummary) => (
                  <option key={t.name} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center gap-2">
              <label className="text-xs text-[var(--muted)]">Rows:</label>
              <input
                type="number"
                value={ds.rows}
                onChange={(e) =>
                  updateDataset(dsIndex, (d) => ({
                    ...d,
                    rows: Math.max(1, Math.min(100000, Number(e.target.value) || 1)),
                  }))
                }
                className="w-20 bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1 text-xs text-[var(--text)]"
                min={1}
                max={100000}
              />
            </div>

            {mode === "grouped" && ds.group_config && (
              <>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1">
                    <label className="text-xs text-[var(--muted)]">Groups:</label>
                    <input
                      type="number"
                      value={ds.group_config.num_groups}
                      onChange={(e) =>
                        updateDataset(dsIndex, (d) => ({
                          ...d,
                          group_config: d.group_config
                            ? { ...d.group_config, num_groups: Math.max(1, Number(e.target.value) || 1) }
                            : d.group_config,
                        }))
                      }
                      className="w-14 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-xs text-[var(--text)]"
                      min={1}
                    />
                  </div>
                  <div className="flex items-center gap-1">
                    <label className="text-xs text-[var(--muted)]">Split %:</label>
                    <input
                      type="number"
                      value={ds.group_config.split_pct}
                      onChange={(e) =>
                        updateDataset(dsIndex, (d) => ({
                          ...d,
                          group_config: d.group_config
                            ? { ...d.group_config, split_pct: Math.max(1, Math.min(100, Number(e.target.value) || 100)) }
                            : d.group_config,
                        }))
                      }
                      className="w-14 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-xs text-[var(--text)]"
                      min={1}
                      max={100}
                    />
                  </div>
                </div>

                {/* Parent fields */}
                <div>
                  <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-wider mb-1">Parent Fields</p>
                  <div className="flex flex-col gap-1 overflow-y-auto max-h-40">
                    <DndContext collisionDetection={closestCenter} onDragEnd={(e) => {
                      const { active, over } = e;
                      if (over && active.id !== over.id) {
                        const oldIndex = parseInt(active.id.toString().split("-")[3]);
                        const newIndex = parseInt(over.id.toString().split("-")[3]);
                        const gc = datasets[dsIndex].group_config;
                        if (gc) {
                          const moved = arrayMove(gc.parent_fields, oldIndex, newIndex);
                          updateDataset(dsIndex, (d) => ({
                            ...d,
                            group_config: { ...gc, parent_fields: moved },
                          }));
                        }
                      }
                    }}>
                      <SortableContext items={(ds.group_config.parent_fields ?? []).map((_, i) => `parent-${dsIndex}-${i}`)} strategy={verticalListSortingStrategy}>
                        {(ds.group_config.parent_fields ?? []).map((field, fIndex) => (
                          <SortableFieldRow
                            key={`parent-${dsIndex}-${fIndex}`}
                            field={field}
                            index={fIndex}
                            dsIndex={dsIndex}
                            onChange={(dsIdx, fi, updater) => {
                              const gc = datasets[dsIdx].group_config;
                              if (gc) {
                                const updated = gc.parent_fields.map((f: FieldDef, i: number) => i === fi ? updater(f) : f);
                                updateDataset(dsIdx, (d) => ({
                                  ...d,
                                  group_config: { ...gc, parent_fields: updated },
                                }));
                              }
                            }}
                            onRemove={(dsIdx, fi) => {
                              const gc = datasets[dsIdx].group_config;
                              if (gc) {
                                updateDataset(dsIdx, (d) => ({
                                  ...d,
                                  group_config: { ...gc, parent_fields: gc.parent_fields.filter((_: FieldDef, i: number) => i !== fi) },
                                }));
                              }
                            }}
                          />
                        ))}
                      </SortableContext>
                    </DndContext>
                    <button
                      onClick={() => {
                        const gc = datasets[dsIndex].group_config;
                        if (gc) {
                          updateDataset(dsIndex, (d) => ({
                            ...d,
                            group_config: { ...gc, parent_fields: [...gc.parent_fields, emptyField()] },
                          }));
                        }
                      }}
                      className="self-start text-xs text-[var(--muted)] hover:text-[var(--text)]"
                    >
                      + Add parent field
                    </button>
                  </div>
                </div>

                {/* Child fields */}
                <div>
                  <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-wider mb-1">Child Fields</p>
                  <div className="flex flex-col gap-1 overflow-y-auto max-h-40">
                    <DndContext collisionDetection={closestCenter} onDragEnd={(e) => {
                      const { active, over } = e;
                      if (over && active.id !== over.id) {
                        const oldIndex = parseInt(active.id.toString().split("-")[3]);
                        const newIndex = parseInt(over.id.toString().split("-")[3]);
                        const gc = datasets[dsIndex].group_config;
                        if (gc) {
                          const moved = arrayMove(gc.child_fields, oldIndex, newIndex);
                          updateDataset(dsIndex, (d) => ({
                            ...d,
                            group_config: { ...gc, child_fields: moved },
                          }));
                        }
                      }
                    }}>
                      <SortableContext items={(ds.group_config.child_fields ?? []).map((_, i) => `child-${dsIndex}-${i}`)} strategy={verticalListSortingStrategy}>
                        {(ds.group_config.child_fields ?? []).map((field, fIndex) => (
                          <SortableFieldRow
                            key={`child-${dsIndex}-${fIndex}`}
                            field={field}
                            index={fIndex}
                            dsIndex={dsIndex}
                            onChange={(dsIdx, fi, updater) => {
                              const gc = datasets[dsIdx].group_config;
                              if (gc) {
                                const updated = gc.child_fields.map((f: FieldDef, i: number) => i === fi ? updater(f) : f);
                                updateDataset(dsIdx, (d) => ({
                                  ...d,
                                  group_config: { ...gc, child_fields: updated },
                                }));
                              }
                            }}
                            onRemove={(dsIdx, fi) => {
                              const gc = datasets[dsIdx].group_config;
                              if (gc) {
                                updateDataset(dsIdx, (d) => ({
                                  ...d,
                                  group_config: { ...gc, child_fields: gc.child_fields.filter((_: FieldDef, i: number) => i !== fi) },
                                }));
                              }
                            }}
                          />
                        ))}
                      </SortableContext>
                    </DndContext>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => {
                          const gc = datasets[dsIndex].group_config;
                          if (gc) {
                            updateDataset(dsIndex, (d) => ({
                              ...d,
                              group_config: { ...gc, child_fields: [...gc.child_fields, emptyField()] },
                            }));
                          }
                        }}
                        className="text-xs text-[var(--muted)] hover:text-[var(--text)]"
                      >
                        + Add child field
                      </button>
                      {ds.group_config.parent_fields.length > 0 && (
                        <select
                          onChange={(e) => {
                            const name = e.target.value;
                            if (!name) return;
                            e.target.value = "";
                            const gc = datasets[dsIndex].group_config;
                            if (!gc) return;
                            const idx = gc.parent_fields.findIndex((f: FieldDef) => f.name === name);
                            if (idx === -1) return;
                            const field = gc.parent_fields[idx];
                            updateDataset(dsIndex, (d) => ({
                              ...d,
                              group_config: {
                                ...gc,
                                parent_fields: gc.parent_fields.filter((_: FieldDef, i: number) => i !== idx),
                                child_fields: [...gc.child_fields, field],
                              },
                            }));
                          }}
                          value=""
                          className="bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-0.5 text-xs text-[var(--muted)]"
                        >
                          <option value="" disabled>Move from parent…</option>
                          {ds.group_config.parent_fields.map((pf: FieldDef) => (
                            <option key={pf.name} value={pf.name}>{pf.name}</option>
                          ))}
                        </select>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}

            {mode === "flat" && (
              <>
                <div className="flex flex-col gap-1 overflow-y-auto max-h-80">
                  <DndContext collisionDetection={closestCenter} onDragEnd={(e) => {
                    const { active, over } = e;
                    if (over && active.id !== over.id) {
                      const oldIndex = parseInt(active.id.toString().split("-")[2]);
                      const newIndex = parseInt(over.id.toString().split("-")[2]);
                      moveField(dsIndex, oldIndex, newIndex);
                    }
                  }}>
                    <SortableContext items={ds.fields.map((_, i) => `field-${dsIndex}-${i}`)} strategy={verticalListSortingStrategy}>
                      {ds.fields.map((field, fIndex) => (
                        <SortableFieldRow
                          key={`field-${dsIndex}-${fIndex}`}
                          field={field}
                          index={fIndex}
                          dsIndex={dsIndex}
                          onChange={updateField}
                          onRemove={removeField}
                        />
                      ))}
                    </SortableContext>
                  </DndContext>
                </div>
                <button
                  onClick={() => addField(dsIndex)}
                  className="self-start text-xs text-[var(--muted)] hover:text-[var(--text)]"
                >
                  + Add field
                </button>
              </>
            )}
          </CollapsibleSection>
        ))}
      </div>
      </SortableContext>
      </DndContext>

      <div className="flex items-center gap-4">
        <button
          onClick={handleGenerate}
          disabled={generateMut.isPending}
          className="px-6 py-2 bg-[var(--accent)] hover:bg-[var(--accent)] disabled:bg-[var(--elevated)] disabled:text-[var(--muted)] rounded text-sm font-medium transition-colors"
        >
          {generateMut.isPending ? "Generating..." : "Generate"}
        </button>

        {generateMut.isError && (
          <p className="text-sm text-[var(--red)]">{generateMut.error.message}</p>
        )}
      </div>

      {results && (
        <>
          {overlapPoolSize > 0 && (
            <p className="text-xs text-[var(--muted)]">
              Shared pool: <span className="text-[var(--accent)]">{overlapPoolSize} rows</span>
              {resultExactFields.length > 0 && (
                <> &bull; Exact fields: <span className="text-[var(--accent)]">{resultExactFields.join(", ")}</span></>
              )}
              {resultBreakCount > 0 && (
                <> &bull; Breaks: <span className="text-[var(--accent)]">{resultBreakCount}</span></>
              )}
            </p>
          )}
          <GenerationResults
            results={results}
            onView={() => onNavigate?.("datasets")}
          />
        </>
      )}
    </div>
  );
}
