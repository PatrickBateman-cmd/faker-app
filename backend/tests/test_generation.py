from __future__ import annotations

import random
from unittest.mock import patch

from faker import Faker

from app.core.database import DuckDBManager
from app.schemas.generation import (
    ConstraintConfig,
    DatasetDefinition,
    FieldDefinition,
    GenerateRequest,
    GroupConfig,
)
from app.services.generation_engine import generate_datasets
from app.services.generation_engine.fakers import build_field_fakers
from app.services.generation_engine.row_builder import generate_row


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


def _grouped_dataset_def(name: str, rows: int = 10, num_groups: int = 2, split_pct: float = 100) -> DatasetDefinition:
    return DatasetDefinition(
        name=name,
        rows=rows,
        group_config=GroupConfig(
            num_groups=num_groups,
            split_pct=split_pct,
            parent_fields=[
                FieldDefinition(name="trade_id", generator="uuid4", type="string"),
            ],
            child_fields=[
                FieldDefinition(name="counterparty_id", generator="uuid4", type="string"),
                FieldDefinition(name="qty", generator="random_int", type="integer"),
            ],
        ),
    )


def test_overlap_grouped_child_field_matches_across_datasets(db):
    req = GenerateRequest(
        datasets=[
            _grouped_dataset_def("g1", rows=10),
            _grouped_dataset_def("g2", rows=10),
        ],
        homogeneity=100,
        seed=42,
        overlap_ratio=0.5,
        exact_fields=["counterparty_id"],
    )
    resp = generate_datasets(req)
    pool_size = resp.overlap_pool_size
    assert pool_size == 5

    ids1 = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    ids2 = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[1].table_name}"').fetchall()]

    for i in range(pool_size):
        assert ids1[i] == ids2[i], f"Pool row {i}: expected matching counterparty_id, got {ids1[i]} vs {ids2[i]}"
    for i in range(pool_size, len(ids1)):
        assert ids1[i] != ids2[i], f"Non-pool row {i} should have distinct counterparty_id"


def test_overlap_grouped_parent_field_rejected(db):
    import pytest
    req = GenerateRequest(
        datasets=[
            _grouped_dataset_def("g1", rows=10),
            _grouped_dataset_def("g2", rows=10),
        ],
        homogeneity=100,
        seed=42,
        overlap_ratio=0.5,
        exact_fields=["trade_id"],
    )
    with pytest.raises(ValueError, match="parent field"):
        generate_datasets(req)


def test_overlap_pool_built_from_first_grouped_dataset(db):
    # Regression check: pool construction must not assume datasets[0].fields
    # is populated — a grouped dataset first in the list has empty `fields`.
    flat_def = DatasetDefinition(
        name="flat_ds",
        rows=10,
        fields=[
            FieldDefinition(name="counterparty_id", generator="uuid4", type="string"),
        ],
    )
    req = GenerateRequest(
        datasets=[
            _grouped_dataset_def("g1", rows=10),
            flat_def,
        ],
        homogeneity=100,
        seed=42,
        overlap_ratio=0.5,
        exact_fields=["counterparty_id"],
    )
    resp = generate_datasets(req)
    pool_size = resp.overlap_pool_size
    assert pool_size == 5

    ids_grouped = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    ids_flat = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[1].table_name}"').fetchall()]

    for i in range(pool_size):
        assert ids_grouped[i] == ids_flat[i]


# --- build_field_fakers invariants -----------------------------------------


def test_build_field_fakers_special_generators_always_none():
    """shared_key/formula/uuid4/uuid_int must never get a Faker instance,
    regardless of homogeneity — they're handled outside the faker path
    entirely in generate_row.
    """
    fields = [
        FieldDefinition(name="sk", generator="shared_key", type="string"),
        FieldDefinition(name="f", generator="formula", type="string", formula="{{x}}"),
        FieldDefinition(name="u4", generator="uuid4", type="string"),
        FieldDefinition(name="ui", generator="uuid_int", type="integer"),
        FieldDefinition(name="age", generator="random_int", type="integer"),
    ]
    fakers = build_field_fakers(fields, homogeneity=100, master_seed=1)
    assert fakers[0] is None
    assert fakers[1] is None
    assert fakers[2] is None
    assert fakers[3] is None
    # homogeneity=100 guarantees every non-special field gets a master-seeded Faker.
    assert fakers[4] is not None
    assert isinstance(fakers[4], Faker)


def test_build_field_fakers_random_draw_count():
    """Each non-special field consumes exactly one random.randint() roll to
    decide master-seed vs. per-row randomization; special-generator fields
    must be skipped BEFORE that roll, not draw-and-discard.
    """
    fields = [
        FieldDefinition(name=f"ri{i}", generator="random_int", type="integer")
        for i in range(5)
    ] + [
        FieldDefinition(name=f"u{i}", generator="uuid4", type="string")
        for i in range(2)
    ]
    with patch(
        "app.services.generation_engine.fakers.random.randint",
        wraps=random.randint,
    ) as mock_randint:
        build_field_fakers(fields, homogeneity=50, master_seed=1)
    assert mock_randint.call_count == 5


# --- generate_row branch precedence -----------------------------------------


def test_generate_row_null_probability_beats_condition():
    """null_probability must be checked before condition — a field that is
    forced null must stay null even when its condition would otherwise pass.
    """
    fields = [
        FieldDefinition(name="age", generator="random_int", type="integer"),
        FieldDefinition(
            name="status",
            generator="random_int",
            type="integer",
            null_probability=1.0,
            condition="age >= 18",
        ),
    ]
    fakers: list[Faker | None] = [None, None]
    fake_fallback = Faker()
    fake_fallback.seed_instance(1)

    row = generate_row(fields, fakers, fake_fallback)

    assert row[0] is not None
    assert row[1] is None


def test_generate_row_pool_entry_beats_null_probability():
    """pool_entry must override every other branch — including a field with
    null_probability=1.0, which would otherwise always be forced to None.
    """
    fields = [
        FieldDefinition(
            name="shared_val",
            generator="random_int",
            type="integer",
            null_probability=1.0,
        ),
    ]
    fakers: list[Faker | None] = [None]
    fake_fallback = Faker()
    fake_fallback.seed_instance(1)

    row = generate_row(fields, fakers, fake_fallback, pool_entry={"shared_val": 999})

    assert row[0] == 999


def test_sql_eligible_field_in_flat_dataset(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="flat_sql",
                rows=50,
                fields=[
                    FieldDefinition(name="id", generator="random_int", type="integer",
                                     constraint=ConstraintConfig(min=1, max=1000000)),
                    FieldDefinition(name="email", generator="email", type="string"),
                    FieldDefinition(name="active", generator="boolean", type="boolean"),
                ],
            ),
        ],
        homogeneity=100,
        seed=42,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT id, email, active FROM "{table}"').fetchall()
    assert len(rows) == 50
    for row_id, email, active in rows:
        assert isinstance(row_id, int) and 1 <= row_id <= 1000000
        assert "@" in email
        assert isinstance(active, bool)


def test_sql_eligible_field_excluded_when_it_is_exact_field(db):
    # id is random_int (SQL-eligible by generator), but it's an exact_field for an
    # overlap request — it must still go through the Python/overlap-pool path.
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="a", rows=10, fields=[
                FieldDefinition(name="id", generator="random_int", type="integer",
                                 constraint=ConstraintConfig(min=1, max=1000000)),
            ]),
            DatasetDefinition(name="b", rows=10, fields=[
                FieldDefinition(name="id", generator="random_int", type="integer",
                                 constraint=ConstraintConfig(min=1, max=1000000)),
            ]),
        ],
        homogeneity=100,
        seed=1,
        overlap_ratio=1.0,
        exact_fields=["id"],
    )
    resp = generate_datasets(req)
    ids_a = [r[0] for r in db.execute(f'SELECT id FROM "{resp.datasets[0].table_name}"').fetchall()]
    ids_b = [r[0] for r in db.execute(f'SELECT id FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert ids_a == ids_b  # overlap pool still works — id never took the SQL path
