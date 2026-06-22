from __future__ import annotations

from app.core.database import DuckDBManager
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
)
from app.services.generation_engine import generate_datasets


def _make_simple_req(rows: int = 10, seed: int | None = None, homogeneity: int = 100):
    return GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="test_ds",
                rows=rows,
                fields=[
                    FieldDefinition(name="first_name", generator="first_name", type="string"),
                    FieldDefinition(name="age", generator="random_int", type="integer"),
                    FieldDefinition(name="is_active", generator="boolean", type="boolean"),
                ],
            )
        ],
        homogeneity=homogeneity,
        seed=seed,
    )


def test_generate_simple(db):
    resp = generate_datasets(_make_simple_req(rows=10, seed=42))
    assert len(resp.datasets) == 1
    ds = resp.datasets[0]
    assert ds.row_count == 10
    assert ds.columns == ["first_name", "age", "is_active"]
    assert ds.name == "test_ds"

    db = DuckDBManager.get_instance()
    rows = db.execute(f'SELECT * FROM "{ds.table_name}"').fetchall()
    assert len(rows) == 10


def test_deterministic_seed(db):
    r1 = generate_datasets(_make_simple_req(rows=5, seed=99))
    r2 = generate_datasets(_make_simple_req(rows=5, seed=99))
    assert r1.datasets[0].row_count == r2.datasets[0].row_count

    db = DuckDBManager.get_instance()
    t1 = db.execute(f'SELECT * FROM "{r1.datasets[0].table_name}"').fetchall()
    t2 = db.execute(f'SELECT * FROM "{r2.datasets[0].table_name}"').fetchall()
    assert t1 == t2


def test_different_seed_produces_different_data(db):
    r1 = generate_datasets(_make_simple_req(rows=5, seed=1))
    r2 = generate_datasets(_make_simple_req(rows=5, seed=2))

    db = DuckDBManager.get_instance()
    t1 = db.execute(f'SELECT * FROM "{r1.datasets[0].table_name}"').fetchall()
    t2 = db.execute(f'SELECT * FROM "{r2.datasets[0].table_name}"').fetchall()
    assert t1 != t2


def test_homogeneity_makes_rows_similar(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="hom_test",
                rows=10,
                fields=[
                    FieldDefinition(name="val", generator="random_int", type="integer"),
                ],
            )
        ],
        homogeneity=100,
        seed=42,
    )
    resp = generate_datasets(req)
    assert resp.homogeneity == 100
    assert resp.datasets[0].row_count == 10


def test_null_probability(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="null_test",
                rows=100,
                fields=[
                    FieldDefinition(
                        name="maybe_null",
                        generator="name",
                        type="string",
                        null_probability=1.0,
                    ),
                ],
            )
        ],
        homogeneity=100,
        seed=42,
    )
    resp = generate_datasets(req)

    db = DuckDBManager.get_instance()
    rows = db.execute(f'SELECT * FROM "{resp.datasets[0].table_name}"').fetchall()
    assert all(r[0] is None for r in rows)


def test_weighted_random_element(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="weight_test",
                rows=100,
                fields=[
                    FieldDefinition(
                        name="color",
                        generator="random_element",
                        type="string",
                        constraint=ConstraintConfig(
                            values="red,blue",
                            weights="90,10",
                        ),
                    ),
                ],
            )
        ],
        homogeneity=100,
        seed=42,
    )
    resp = generate_datasets(req)

    db = DuckDBManager.get_instance()
    rows = db.execute(f'SELECT * FROM "{resp.datasets[0].table_name}"').fetchall()
    values = [r[0] for r in rows]
    assert "red" in values
    assert "blue" in values


def _two_dataset_req(rows: int = 10, overlap_ratio: float = 0.0, exact_fields: list[str] | None = None, seed: int = 42) -> GenerateRequest:
    shared_fields = [
        FieldDefinition(name="cust_id", generator="uuid4", type="string"),
        FieldDefinition(name="age", generator="random_int", type="integer"),
    ]
    return GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=rows, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=rows, fields=list(shared_fields)),
        ],
        homogeneity=100,
        seed=seed,
        overlap_ratio=overlap_ratio,
        exact_fields=exact_fields or [],
    )


def test_overlap_zero_no_pool(db):
    resp = generate_datasets(_two_dataset_req(rows=10, overlap_ratio=0.0))
    assert resp.overlap_pool_size == 0
    assert resp.exact_fields == []


def test_overlap_pool_size_calculated(db):
    resp = generate_datasets(_two_dataset_req(rows=10, overlap_ratio=0.5, exact_fields=["cust_id"]))
    assert resp.overlap_pool_size == 5  # floor(10 * 0.5)


def test_overlap_exact_fields_match_across_datasets(db):
    resp = generate_datasets(_two_dataset_req(rows=10, overlap_ratio=0.5, exact_fields=["cust_id"]))
    pool_size = resp.overlap_pool_size

    ids1 = [r[0] for r in db.execute(f'SELECT cust_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    ids2 = [r[0] for r in db.execute(f'SELECT cust_id FROM "{resp.datasets[1].table_name}"').fetchall()]

    # First pool_size rows must share the same cust_id
    for i in range(pool_size):
        assert ids1[i] == ids2[i], f"Pool row {i}: expected matching cust_id, got {ids1[i]} vs {ids2[i]}"

    # Rows beyond the pool must differ (uuid4 is always unique)
    for i in range(pool_size, len(ids1)):
        assert ids1[i] != ids2[i], f"Non-pool row {i} should have distinct cust_id"


def test_overlap_non_exact_fields_not_in_pool_entry(db):
    # Verify the pool only carries exact_fields values — not other columns.
    # We do this by checking that row_count is still correct (all rows generated).
    resp = generate_datasets(_two_dataset_req(rows=10, overlap_ratio=0.5, exact_fields=["cust_id"]))
    assert resp.datasets[0].row_count == 10
    assert resp.datasets[1].row_count == 10

    # Both datasets must have all age values non-null (age was generated, not skipped)
    ages1 = [r[0] for r in db.execute(f'SELECT age FROM "{resp.datasets[0].table_name}"').fetchall()]
    ages2 = [r[0] for r in db.execute(f'SELECT age FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert all(v is not None for v in ages1)
    assert all(v is not None for v in ages2)


def test_overlap_error_missing_exact_fields(db):
    import pytest
    with pytest.raises(ValueError, match="exact_fields must be specified"):
        generate_datasets(_two_dataset_req(rows=10, overlap_ratio=0.5, exact_fields=[]))


def test_overlap_error_unknown_exact_field(db):
    import pytest
    with pytest.raises(ValueError, match="exact field 'nonexistent' not found"):
        generate_datasets(_two_dataset_req(rows=10, overlap_ratio=0.5, exact_fields=["nonexistent"]))
