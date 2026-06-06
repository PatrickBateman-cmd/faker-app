import { DndContext, closestCenter, type DragEndEvent } from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { fetchTemplate, fetchTemplates, generateDatasets } from "../../api/generation";
import { GenerationResults } from "../ResultsViewer/ResultsViewer";
import type {
  DatasetDefinition,
  DatasetResult,
  FieldDef,
  TemplateSummary,
} from "../../types/generation";

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

function emptyDataset(name?: string): DatasetDefinition {
  return {
    name: name || "",
    rows: 100,
    fields: [emptyField()],
  };
}

export function GenerationControls({ onNavigate, pendingTemplate: externalTemplate }: { onNavigate?: (page: string) => void; pendingTemplate?: string | null }) {
  const [datasetCount, setDatasetCount] = useState(1);
  const [datasets, setDatasets] = useState<DatasetDefinition[]>([emptyDataset("Dataset 1")]);
  const [homogeneity, setHomogeneity] = useState(50);
  const [seed, setSeed] = useState("");
  const [results, setResults] = useState<DatasetResult[] | null>(null);

  const templates = useQuery({
    queryKey: ["templates"],
    queryFn: fetchTemplates,
  });

  const generateMut = useMutation({
    mutationFn: generateDatasets,
    onSuccess: (data) => {
      setResults(data.datasets);
    },
  });

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

  function updateField(dsIndex: number, fieldIndex: number, updater: (f: FieldDef) => FieldDef) {
    updateDataset(dsIndex, (d) => ({
      ...d,
      fields: d.fields.map((f, i) => (i === fieldIndex ? updater(f) : f)),
    }));
  }

  function applyTemplate(dsIndex: number, templateName: string) {
    fetchTemplate(templateName).then((t) => {
      updateDataset(dsIndex, (d) => ({
        ...d,
        name: t.name,
        template: t.name,
        fields: t.fields.map((f) => ({
          name: f.name,
          generator: f.generator,
          type: f.type,
          unique: f.unique,
          formula: f.formula,
          constraint: f.constraint || null,
        })),
      }));
    });
  }

  useEffect(() => {
    if (externalTemplate) {
      applyTemplate(0, externalTemplate);
    }
  }, [externalTemplate]);

  function handleGenerate() {
    const seedVal = seed ? parseInt(seed, 10) : undefined;
    generateMut.mutate({
      datasets: datasets.map((d) => ({
        ...d,
        rows: d.rows || 100,
      })),
      homogeneity,
      seed: seedVal && !isNaN(seedVal) ? seedVal : undefined,
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
      </div>

      <div className="flex gap-4 flex-1 min-h-0 overflow-auto">
        {datasets.map((ds, dsIndex) => (
          <div
            key={dsIndex}
            className="flex-1 min-w-0 bg-[var(--surface)] border border-[var(--border)] rounded p-4 flex flex-col gap-3"
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
          </div>
        ))}
      </div>

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
        <GenerationResults
          results={results}
          onView={() => onNavigate?.("datasets")}
        />
      )}
    </div>
  );
}
