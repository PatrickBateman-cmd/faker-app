import { useState } from "react";
import { deriveBalances } from "../../api/balance";
import type { BalanceDeriveResponse } from "../../types/balance";
import type { FieldBreakConfig } from "../../types/generation";
import { useToast } from "../../hooks/useToast";

const BALANCE_BREAK_FIELDS: FieldBreakConfig["field_name"][] = ["closing_balance", "net_movement"];
const BREAK_STYLE_OPTIONS: FieldBreakConfig["break_style"][] = ["drift", "different", "null"];

function emptyBalanceBreak(): FieldBreakConfig {
  return { field_name: "closing_balance", break_rate: 10, break_style: "drift", drift_pct: 2 };
}

interface Props {
  datasetId: string;
  columns: string[];
  onResult: (result: BalanceDeriveResponse) => void;
  onBack: () => void;
}

export default function BalancePanel({ datasetId, columns, onResult, onBack }: Props) {
  const { addToast } = useToast();
  const [name, setName] = useState("");
  const [accountFields, setAccountFields] = useState<string[]>([]);
  const [currencyField, setCurrencyField] = useState("currency");
  const [dateField, setDateField] = useState("transaction_date");
  const [amountField, setAmountField] = useState("amount");
  const [directionField, setDirectionField] = useState("transaction_type");
  const [creditValues, setCreditValues] = useState("Credit, Deposit, Refund");
  const [debitValues, setDebitValues] = useState("Debit, Withdrawal, Payment, Transfer");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [openingBalanceSeed, setOpeningBalanceSeed] = useState("");
  const [balanceBreaks, setBalanceBreaks] = useState<FieldBreakConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastResult, setLastResult] = useState<BalanceDeriveResponse | null>(null);

  const toggleAccountField = (col: string) => {
    setAccountFields((prev) =>
      prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col]
    );
  };

  function updateBreak(index: number, updater: (fb: FieldBreakConfig) => FieldBreakConfig) {
    setBalanceBreaks((prev) => prev.map((fb, i) => (i === index ? updater(fb) : fb)));
  }

  function removeBreak(index: number) {
    setBalanceBreaks((prev) => prev.filter((_, i) => i !== index));
  }

  const handleSubmit = async () => {
    if (!name.trim()) {
      setError("Result name is required");
      return;
    }
    if (accountFields.length === 0) {
      setError("Select at least one account hierarchy column");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const seedVal = openingBalanceSeed.trim() ? Number(openingBalanceSeed) : undefined;
      const result = await deriveBalances(datasetId, {
        name: name.trim(),
        account_fields: accountFields,
        currency_field: currencyField.trim() || undefined,
        date_field: dateField.trim() || undefined,
        amount_field: amountField.trim() || undefined,
        direction_field: directionField.trim() || undefined,
        credit_values: creditValues.split(",").map((s) => s.trim()).filter(Boolean),
        debit_values: debitValues.split(",").map((s) => s.trim()).filter(Boolean),
        start_date: startDate.trim() || undefined,
        end_date: endDate.trim() || undefined,
        opening_balance_seed: seedVal !== undefined && !isNaN(seedVal) ? seedVal : undefined,
        balance_breaks: balanceBreaks.map((fb) => ({
          ...fb,
          break_rate: fb.break_rate / 100,
          drift_pct: fb.drift_pct / 100,
        })),
      });
      setLastResult(result);
      setOpeningBalanceSeed(String(result.opening_balance_seed));
      onResult(result);
      addToast("Balances derived", "success");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      setError(msg);
      addToast(msg, "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Derive Balances</h3>
        <button onClick={onBack} className="text-sm text-indigo-400 hover:text-indigo-300">
          &larr; Back to datasets
        </button>
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">Result name</label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. ledger_balances"
          className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-3 py-2 text-sm"
        />
      </div>

      <div>
        <label className="block text-sm font-medium text-[var(--text)] mb-1">
          Account hierarchy columns (order matters)
        </label>
        <div className="flex flex-wrap gap-2">
          {columns.map((col) => (
            <button
              key={col}
              onClick={() => toggleAccountField(col)}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                accountFields.includes(col)
                  ? "bg-indigo-600 text-white"
                  : "bg-[var(--elevated)] text-[var(--text)] hover:bg-[var(--elevated)]"
              }`}
            >
              {col}
              {accountFields.includes(col) && ` (${accountFields.indexOf(col) + 1})`}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Currency field</label>
          <input
            type="text"
            value={currencyField}
            onChange={(e) => setCurrencyField(e.target.value)}
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Date field</label>
          <input
            type="text"
            value={dateField}
            onChange={(e) => setDateField(e.target.value)}
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Amount field</label>
          <input
            type="text"
            value={amountField}
            onChange={(e) => setAmountField(e.target.value)}
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Direction field</label>
          <input
            type="text"
            value={directionField}
            onChange={(e) => setDirectionField(e.target.value)}
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Credit values</label>
          <input
            type="text"
            value={creditValues}
            onChange={(e) => setCreditValues(e.target.value)}
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Debit values</label>
          <input
            type="text"
            value={debitValues}
            onChange={(e) => setDebitValues(e.target.value)}
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">Start date (blank = earliest)</label>
          <input
            type="text"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            placeholder="YYYY-MM-DD"
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-[var(--muted)] mb-1">End date (blank = latest)</label>
          <input
            type="text"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            placeholder="YYYY-MM-DD"
            className="w-full bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs text-[var(--muted)] mb-1">
          Opening balance seed (blank = random; reuse the value returned below on the paired
          ledger/street derivation to align both sides)
        </label>
        <input
          type="number"
          value={openingBalanceSeed}
          onChange={(e) => setOpeningBalanceSeed(e.target.value)}
          placeholder="random"
          className="w-48 bg-[var(--elevated)] border border-[var(--border)] rounded px-2 py-1.5 text-sm"
        />
      </div>

      <div className="flex flex-col gap-2 bg-[var(--surface)] border border-[var(--border)] rounded p-3">
        <p className="text-xs font-semibold text-[var(--accent)] uppercase tracking-wider">
          Balance Breaks
        </p>
        {balanceBreaks.length === 0 && (
          <p className="text-xs text-[var(--muted)]">
            No break rules — closing balances will be exactly correct.
          </p>
        )}
        {balanceBreaks.map((fb, i) => (
          <div key={i} className="flex items-center gap-2 text-xs">
            <select
              value={fb.field_name}
              onChange={(e) => updateBreak(i, (f) => ({ ...f, field_name: e.target.value }))}
              className="w-36 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)]"
            >
              {BALANCE_BREAK_FIELDS.map((f) => (
                <option key={f} value={f}>{f}</option>
              ))}
            </select>
            <label className="text-[var(--muted)]">Rate:</label>
            <input
              type="range"
              min={0}
              max={100}
              value={fb.break_rate}
              onChange={(e) => updateBreak(i, (f) => ({ ...f, break_rate: Number(e.target.value) }))}
              className="w-20"
            />
            <span className="text-[var(--accent)] w-9">{fb.break_rate}%</span>
            <select
              value={fb.break_style}
              onChange={(e) =>
                updateBreak(i, (f) => ({ ...f, break_style: e.target.value as FieldBreakConfig["break_style"] }))
              }
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
                  onChange={(e) =>
                    updateBreak(i, (f) => ({ ...f, drift_pct: Math.max(1, Number(e.target.value) || 1) }))
                  }
                  className="w-14 bg-[var(--elevated)] border border-[var(--border)] rounded px-1.5 py-1 text-[var(--text)]"
                />
                <span className="text-[var(--muted)]">%</span>
              </>
            )}
            <button
              onClick={() => removeBreak(i)}
              className="text-[var(--muted)] hover:text-[var(--red)] px-1"
              title="Remove break rule"
            >
              x
            </button>
          </div>
        ))}
        <button
          onClick={() => setBalanceBreaks((prev) => [...prev, emptyBalanceBreak()])}
          className="self-start text-xs text-[var(--muted)] hover:text-[var(--text)]"
        >
          + Add break rule
        </button>
      </div>

      {error && <p className="text-[var(--red)] text-sm">{error}</p>}

      {lastResult && (
        <p className="text-xs text-[var(--muted)]">
          Opening balance seed used:{" "}
          <span className="text-[var(--accent)] font-mono">{lastResult.opening_balance_seed}</span>
          {" — "}pass it to the paired derivation to align both sides.
        </p>
      )}

      <button
        onClick={handleSubmit}
        disabled={loading}
        className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:bg-[var(--elevated)] text-white font-medium py-2 px-4 rounded text-sm transition-colors"
      >
        {loading ? "Deriving..." : "Derive Balances"}
      </button>
    </div>
  );
}
