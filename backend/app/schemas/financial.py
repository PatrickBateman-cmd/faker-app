from pydantic import BaseModel, Field


class EnrichmentDef(BaseModel):
    field_name: str
    source: str = Field(..., pattern=r"^(quote|info)$")


class EnrichRequest(BaseModel):
    source_dataset_id: str
    ticker_column: str
    enrichments: list[EnrichmentDef]
    name: str | None = None


class EnrichResponse(BaseModel):
    dataset_id: str
    name: str
    table_name: str
    row_count: int
    columns: list[str]
    source_dataset: str
