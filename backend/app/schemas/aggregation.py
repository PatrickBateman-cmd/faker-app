from pydantic import BaseModel, Field


class AggregationDef(BaseModel):
    column: str
    function: str = Field(
        ..., pattern=r"^(sum|avg|min|max|count|count_distinct|first|last)$"
    )
    alias: str | None = None


class AggregateRequest(BaseModel):
    name: str
    group_by: list[str] = Field(..., min_length=1)
    aggregations: list[AggregationDef] = Field(..., min_length=1)


class OrderByDef(BaseModel):
    column: str
    direction: str = Field(default="desc", pattern=r"^(asc|desc)$")


class DedupRequest(BaseModel):
    name: str
    keys: list[str] = Field(..., min_length=1)
    strategy: str = Field(
        default="keep_first",
        pattern=r"^(keep_first|keep_last|keep_none)$",
    )
    order_by: OrderByDef | None = None


class TransformResponse(BaseModel):
    dataset_id: str
    name: str
    table_name: str
    row_count: int
    columns: list[str]
    source_dataset: str
    transform_type: str
