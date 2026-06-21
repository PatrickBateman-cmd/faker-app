from __future__ import annotations

from pydantic import BaseModel


class KaggleDatasetItem(BaseModel):
    ref: str
    title: str
    size: int
    last_updated: str
    download_count: int
    vote_count: int
    usability_rating: float
    file_count: int


class KaggleFile(BaseModel):
    name: str
    size: int
    creation_date: str


class KaggleImportRequest(BaseModel):
    owner: str
    slug: str
    file_name: str
    dataset_name: str | None = None
    max_rows: int | None = None


class KaggleImportResponse(BaseModel):
    dataset_id: str
    name: str
    table_name: str
    row_count: int
    columns: list[str]
