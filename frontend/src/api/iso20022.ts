import type { DomainInfo, MessageInfo, XsdParsedResponse } from "../types/iso20022";

const BASE = "/api/iso20022";

export async function fetchDomains(): Promise<DomainInfo[]> {
  const res = await fetch(`${BASE}/domains`);
  if (!res.ok) throw new Error("Failed to fetch domains");
  return res.json();
}

export async function fetchMessages(
  domain?: string,
): Promise<MessageInfo[]> {
  const params = new URLSearchParams();
  if (domain) params.set("domain", domain);
  const res = await fetch(`${BASE}/messages?${params}`);
  if (!res.ok) throw new Error("Failed to fetch messages");
  return res.json();
}

export async function searchMessages(q: string): Promise<MessageInfo[]> {
  const res = await fetch(`${BASE}/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error("Search failed");
  }
  return res.json();
}

export async function fetchXsdParsed(
  messageId: string,
): Promise<XsdParsedResponse> {
  const res = await fetch(`${BASE}/messages/${encodeURIComponent(messageId)}/xsd`);
  if (!res.ok) throw new Error("Failed to parse XSD");
  return res.json();
}
