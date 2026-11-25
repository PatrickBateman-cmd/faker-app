import type { BalanceDeriveRequest, BalanceDeriveResponse } from "../types/balance";

export async function deriveBalances(
  datasetId: string,
  body: BalanceDeriveRequest
): Promise<BalanceDeriveResponse> {
  const res = await fetch(`/api/datasets/${datasetId}/balances`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Balance derivation failed" }));
    throw new Error(err.detail);
  }
  return res.json();
}
