import type { GenerateRequest, GenerateResponse, TemplateSummary } from "../types/generation";

export async function fetchTemplates(): Promise<TemplateSummary[]> {
  const res = await fetch("/api/templates");
  if (!res.ok) throw new Error("Failed to fetch templates");
  return res.json();
}

export async function fetchTemplate(name: string): Promise<TemplateSummary & { fields: any[] }> {
  const res = await fetch(`/api/templates/${encodeURIComponent(name)}`);
  if (!res.ok) throw new Error("Template not found");
  return res.json();
}

export async function generateDatasets(body: GenerateRequest): Promise<GenerateResponse> {
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Generation failed" }));
    throw new Error(err.detail);
  }
  return res.json();
}
