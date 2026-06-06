import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { fetchDomains, fetchMessages, fetchXsdParsed, searchMessages } from "../../api/iso20022";
import { createTemplate } from "../../api/templates";
import type { ParsedField } from "../../types/iso20022";

export function Iso20022Panel({ onApply }: { onApply?: (name: string) => void }) {
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [selectedMessage, setSelectedMessage] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const domains = useQuery({
    queryKey: ["iso20022", "domains"],
    queryFn: fetchDomains,
  });

  const messages = useQuery({
    queryKey: ["iso20022", "messages", selectedDomain],
    queryFn: () => fetchMessages(selectedDomain ?? undefined),
    enabled: !!selectedDomain && !debouncedQuery,
  });

  const searchResults = useQuery({
    queryKey: ["iso20022", "search", debouncedQuery],
    queryFn: () => searchMessages(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
  });

  const xsdDetail = useQuery({
    queryKey: ["iso20022", "xsd", selectedMessage],
    queryFn: () => fetchXsdParsed(selectedMessage!),
    enabled: !!selectedMessage,
  });

  function handleSearch(value: string) {
    setSearchQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(value);
      setSelectedDomain(null);
      setSelectedMessage(null);
    }, 300);
  }

  function clearSearch() {
    setSearchQuery("");
    setDebouncedQuery("");
    setSelectedMessage(null);
  }

  function escapeXml(s: string): string {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&apos;");
  }

  function mapXsdType(xsdType: string): string {
    const t = xsdType.toLowerCase();
    if (/decimal|amount|price|rate/.test(t)) return "float";
    if (/(numeric|integer|year|index)/.test(t)) return "integer";
    if (/date|time|timestamp/.test(t)) return "date";
    if (/boolean|indicator/.test(t)) return "boolean";
    return "string";
  }

  function flattenFields(fields: ParsedField[], prefix = ""): Array<{ name: string; type: string; generator: string; values: string[] | null }> {
    const result: Array<{ name: string; type: string; generator: string; values: string[] | null }> = [];
    for (const f of fields) {
      const fullName = prefix ? `${prefix}.${f.name}` : f.name;
      result.push({
        name: fullName,
        type: mapXsdType(f.xsd_type),
        generator: f.mapped_generator,
        values: f.enumeration_values,
      });
      if (f.nested_fields) {
        result.push(...flattenFields(f.nested_fields, fullName));
      }
    }
    return result;
  }

  function buildTemplateXml(messageId: string, messageName: string, fields: ParsedField[]): string {
    const name = `${messageId} - ${messageName}`;
    const flatFields = flattenFields(fields);
    let xml = `<template name="${escapeXml(name)}" category="ISO 20022">\n`;
    xml += `  <meta description="${escapeXml(`Generated from ISO 20022 message ${messageId}`)}" version="1.0"/>\n\n`;
    for (const f of flatFields) {
      if (f.values && f.values.length > 0) {
        xml += `  <field name="${escapeXml(f.name)}" type="${f.type}" generator="${escapeXml(f.generator)}">\n`;
        xml += `    <constraint values="${escapeXml(f.values.join(","))}"/>\n`;
        xml += `  </field>\n`;
      } else {
        xml += `  <field name="${escapeXml(f.name)}" type="${f.type}" generator="${escapeXml(f.generator)}"/>\n`;
      }
    }
    xml += `</template>`;
    return xml;
  }

  async function handleSaveAsTemplate() {
    if (!xsdDetail.data) return;
    setSaving(true);
    setSaveError(null);
    try {
      const xml = buildTemplateXml(xsdDetail.data.message_id, xsdDetail.data.message_name, xsdDetail.data.fields);
      const template = await createTemplate(xml);
      onApply?.(template.name);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const displayMessages = debouncedQuery.length >= 2 ? (searchResults.data ?? []) : (messages.data ?? []).slice(0, 100);

  return (
    <div className="flex gap-6 h-full">
      <div className="w-56 shrink-0 flex flex-col gap-2">
        <div className="relative mb-1">
          <input
            value={searchQuery}
            onChange={(e) => handleSearch(e.target.value)}
            placeholder="Search messages..."
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder:text-[var(--muted)] focus:outline-none focus:border-cyan-700"
          />
          {searchQuery && (
            <button
              onClick={clearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--muted)] hover:text-[var(--text)] text-xs"
            >
              ✕
            </button>
          )}
        </div>
        <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-1">
          {debouncedQuery ? "Search Results" : "Domains"}
        </h3>
        {!debouncedQuery && (
          <div className="flex flex-col gap-1">
            {(domains.data ?? []).map((d) => (
              <button
                key={d.id}
                onClick={() => {
                  setSelectedDomain(d.id);
                  setSelectedMessage(null);
                }}
                className={`text-left px-3 py-2 rounded text-sm transition-colors ${
                  selectedDomain === d.id
                    ? "bg-[var(--selection)] text-[var(--accent)] border border-[var(--accent)]"
                    : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--elevated)] border border-transparent"
                }`}
              >
                {d.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="w-72 shrink-0 flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-[var(--muted)] uppercase tracking-wider mb-1">
          {debouncedQuery
            ? `Messages (${displayMessages.length})`
            : "Messages"}
        </h3>
        {!selectedDomain && !debouncedQuery && (
          <p className="text-sm text-[var(--muted)]">Select a domain or search</p>
        )}
        {(messages.isPending || searchResults.isPending) && (
          <p className="text-sm text-[var(--muted)]">Loading...</p>
        )}
        {(messages.error || searchResults.error) && (
          <p className="text-sm text-[var(--red)]">
            {(messages.error ?? searchResults.error)!.message}
          </p>
        )}
        <div className="flex flex-col gap-1 overflow-y-auto max-h-[70vh]">
          {displayMessages.map((m) => (
            <button
              key={m.message_id}
              onClick={() => setSelectedMessage(m.message_id)}
              className={`text-left px-3 py-2 rounded text-sm transition-colors ${
                selectedMessage === m.message_id
                  ? "bg-[var(--selection)] text-[var(--accent)] border border-[var(--accent)]"
                  : "text-[var(--muted)] hover:text-[var(--text)] hover:bg-[var(--elevated)] border border-transparent"
              }`}
            >
              <div className="truncate font-mono text-xs">{m.message_id}</div>
              <div className="truncate text-xs text-[var(--muted)]">
                {m.message_name}
              </div>
              {debouncedQuery && m.business_area && (
                <div className="truncate text-xs text-[var(--muted)]">{m.business_area}</div>
              )}
            </button>
          ))}
          {debouncedQuery && displayMessages.length === 0 && !searchResults.isPending && (
            <p className="text-sm text-[var(--muted)]">No results found</p>
          )}
        </div>
      </div>

      <div className="flex-1 min-w-0 overflow-y-auto">
        {!selectedMessage && (
          <p className="text-sm text-[var(--muted)]">
            Select a domain and message to view its XSD-parsed fields
          </p>
        )}
        {xsdDetail.isPending && (
          <p className="text-sm text-[var(--muted)]">Downloading and parsing XSD...</p>
        )}
        {xsdDetail.error && (
          <div className="text-sm text-[var(--red)]">
            <p>Failed to parse XSD: {xsdDetail.error.message}</p>
            <p className="text-[var(--muted)] mt-2">
              This may happen if the ISO 20022 site is unreachable or the XSD
              format is unexpected. Try another message.
            </p>
          </div>
        )}
        {xsdDetail.data && (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-xl font-semibold text-[var(--text)]">
                {xsdDetail.data.message_name}
              </h2>
              <p className="text-sm text-[var(--muted)] font-mono">
                {xsdDetail.data.message_id}
              </p>
              {xsdDetail.data.namespace && (
                <p className="text-xs text-[var(--muted)] truncate max-w-xl">
                  {xsdDetail.data.namespace}
                </p>
              )}
            </div>

            <div className="flex items-center gap-4">
              <span className="text-sm text-[var(--muted)]">
                {xsdDetail.data.fields.length} fields parsed
              </span>
              <button
                onClick={handleSaveAsTemplate}
                disabled={saving}
                className="px-3 py-1 text-xs font-medium bg-[var(--accent)] text-white rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {saving ? "Saving..." : "Save as Template"}
              </button>
              {saveError && (
                <span className="text-xs text-[var(--red)]">{saveError}</span>
              )}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[var(--muted)] border-b border-[var(--border)]">
                    <th className="pb-2 pr-4 font-medium">Field</th>
                    <th className="pb-2 pr-4 font-medium">XSD Type</th>
                    <th className="pb-2 pr-4 font-medium">Mapped Generator</th>
                    <th className="pb-2 pr-4 font-medium">Occurs</th>
                    <th className="pb-2 font-medium">Details</th>
                  </tr>
                </thead>
                <tbody className="text-[var(--text)]">
                  {xsdDetail.data.fields.map((f) => (
                    <FieldRow key={f.name} field={f} depth={0} />
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function FieldRow({ field, depth }: { field: ParsedField; depth: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasNested = field.nested_fields && field.nested_fields.length > 0;

  return (
    <>
      <tr className="border-b border-[var(--border)] hover:bg-[var(--surface)]">
        <td
          className="py-2 pr-4"
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
        >
          <div className="flex items-center gap-1">
            {hasNested && (
              <button
                onClick={() => setExpanded(!expanded)}
                className="text-[var(--muted)] hover:text-[var(--text)] text-xs"
              >
                {expanded ? "▾" : "▸"}
              </button>
            )}
            <span className={depth > 0 ? "text-[var(--muted)]" : ""}>
              {field.name}
            </span>
          </div>
        </td>
        <td className="py-2 pr-4 text-[var(--muted)] font-mono text-xs">
          {field.xsd_type}
        </td>
        <td className="py-2 pr-4">
          <span className="text-[var(--accent)]">{field.mapped_generator}</span>
        </td>
        <td className="py-2 pr-4 text-[var(--muted)] text-xs">
          {field.min_occurs}..{field.max_occurs}
        </td>
        <td className="py-2 text-[var(--muted)] text-xs max-w-xs">
          {field.enumeration_values && (
            <span className="text-amber-500">
              enum({field.enumeration_values.slice(0, 5).join(", ")}
              {field.enumeration_values.length > 5 ? "..." : ""})
            </span>
          )}
          {field.documentation && !field.enumeration_values && (
            <span className="truncate block max-w-48" title={field.documentation}>
              {field.documentation}
            </span>
          )}
        </td>
      </tr>
      {expanded &&
        hasNested &&
        field.nested_fields!.map((nf) => (
          <FieldRow key={nf.name} field={nf} depth={depth + 1} />
        ))}
    </>
  );
}
