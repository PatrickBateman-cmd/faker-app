from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.generation import FieldBreakConfig


class BalanceDeriveRequest(BaseModel):
    name: str
    account_fields: list[str] = Field(..., min_length=1)
    currency_field: str = "currency"
    date_field: str = "transaction_date"
    amount_field: str = "amount"
    direction_field: str = "transaction_type"
    credit_values: list[str] = Field(default_factory=lambda: ["Credit", "Deposit", "Refund"])
    debit_values: list[str] = Field(
        default_factory=lambda: ["Debit", "Withdrawal", "Payment", "Transfer"]
    )
    start_date: str | None = None
    end_date: str | None = None
    opening_balance_seed: float | None = None
    balance_breaks: list[FieldBreakConfig] = Field(default_factory=list)


class BalanceDeriveResponse(BaseModel):
    dataset_id: str
    name: str
    table_name: str
    row_count: int
    columns: list[str]
    source_dataset: str
    transform_type: str = "balance"
    opening_balance_seed: float
    start_date: str
    end_date: str
    run_id: int | None = None
    break_count: int = 0
