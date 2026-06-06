from __future__ import annotations

import os

import pytest

from app.schemas.generation import (
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
)
from app.services.export_service import export_csv, export_parquet, export_xlsx
from app.services.generation_engine import generate_datasets


def _generate_simple(db) -> str:
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="export_test",
                rows=10,
                fields=[
                    FieldDefinition(name="name", generator="name", type="string"),
                    FieldDefinition(name="age", generator="random_int", type="integer"),
                ],
            )
        ],
        homogeneity=100,
        seed=42,
    )
    return generate_datasets(req).datasets[0].dataset_id


def test_export_csv(db):
    ds_id = _generate_simple(db)
    path = export_csv(ds_id)
    assert os.path.exists(path)
    assert path.endswith(".csv")
    assert os.path.getsize(path) > 0
    os.unlink(path)


def test_export_parquet(db):
    ds_id = _generate_simple(db)
    path = export_parquet(ds_id)
    assert os.path.exists(path)
    assert path.endswith(".parquet")
    assert os.path.getsize(path) > 0
    os.unlink(path)


def test_export_xlsx(db):
    ds_id = _generate_simple(db)
    path = export_xlsx(ds_id)
    assert os.path.exists(path)
    assert path.endswith(".xlsx")
    assert os.path.getsize(path) > 0
    os.unlink(path)


def test_export_nonexistent(db):
    with pytest.raises(ValueError, match="not found"):
        export_csv("nonexistent-id")

    with pytest.raises(ValueError, match="not found"):
        export_parquet("nonexistent-id")

    with pytest.raises(ValueError, match="not found"):
        export_xlsx("nonexistent-id")
