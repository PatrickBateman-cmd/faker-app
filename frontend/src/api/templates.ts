import type { Template, TemplateSummary } from "../types/template";

const BASE = "/api/templates";

export async function fetchTemplates(): Promise<TemplateSummary[]> {
  const res = await fetch(BASE);
  if (!res.ok) throw new Error("Failed to fetch templates");
  return res.json();
}

export async function fetchTemplate(name: string): Promise<Template> {
  const res = await fetch(`${BASE}/${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error("Template not found");
  return res.json();
}

export async function createTemplate(xmlContent: string): Promise<Template> {
  const res = await fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ xml_content: xmlContent }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Create failed" }));
    throw new Error(err.detail);
  }
  return res.json();
}

export async function deleteTemplate(name: string): Promise<void> {
  const res = await fetch(`${BASE}/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Delete failed");
}
