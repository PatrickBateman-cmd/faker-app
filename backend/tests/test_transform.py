from __future__ import annotations

import pytest

from app.core.database import DuckDBManager
from app.schemas.aggregation import AggregateRequest, AggregationDef, DedupRequest
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
)
from app.services.generation_engine import generate_datasets
from app.services.transform_service import aggregate_dataset, dedup_dataset


def _generate_source(db, rows: int = 20, seed: int = 42) -> str:
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="source",
                rows=rows,
                fields=[
                    FieldDefinition(
                        name="category",
                        generator="random_element",
                        type="string",
                        constraint=ConstraintConfig(values="A,B"),
                    ),
                    FieldDefinition(
                        name="value",
                        generator="random_int",
                        type="integer",
                    ),
                ],
            )
        ],
        homogeneity=100,
        seed=seed,
    )
    return generate_datasets(req).datasets[0].dataset_id


def test_aggregate(db):
    ds_id = _generate_source(db)

    result = aggregate_dataset(
        ds_id,
        AggregateRequest(
            name="agg_result",
            group_by=["category"],
            aggregations=[AggregationDef(column="value", function="sum", alias="total")],
        ),
    )
    assert result.row_count == 2
    assert result.transform_type == "aggregate"
    assert "category" in result.columns
    assert "total" in result.columns

    rows = DuckDBManager.get_instance().execute(
        f'SELECT * FROM "{result.table_name}" ORDER BY category'
    ).fetchall()
    assert len(rows) == 2


def test_dedup_keep_first(db):
    ds_id = _generate_source(db)

    result = dedup_dataset(
        ds_id,
        DedupRequest(name="deduped", keys=["category"], strategy="keep_first"),
    )
    assert result.row_count == 2
    assert result.transform_type == "dedup"


def test_dedup_keep_last(db):
    ds_id = _generate_source(db)

    result = dedup_dataset(
        ds_id,
        DedupRequest(name="deduped_last", keys=["category"], strategy="keep_last"),
    )
    assert result.row_count == 2
    assert result.transform_type == "dedup"


def test_aggregate_nonexistent_dataset(db):
    with pytest.raises(ValueError, match="not found"):
        aggregate_dataset(
            "nonexistent",
            AggregateRequest(
                name="fail",
                group_by=["x"],
                aggregations=[AggregationDef(column="y", function="count", alias="n")],
            ),
        )


def test_dedup_nonexistent_dataset(db):
    with pytest.raises(ValueError, match="not found"):
        dedup_dataset(
            "nonexistent",
            DedupRequest(name="fail", keys=["x"], strategy="keep_first"),
        )
