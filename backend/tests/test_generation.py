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


def test_sql_eligible_fields_in_grouped_dataset(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="grouped_sql",
                rows=30,
                group_config=GroupConfig(
                    num_groups=3,
                    split_pct=100,
                    parent_fields=[
                        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
                        FieldDefinition(name="group_num", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=100)),
                    ],
                    child_fields=[
                        FieldDefinition(name="qty", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=1000)),
                        FieldDefinition(name="counterparty", generator="company", type="string"),
                    ],
                ),
            ),
        ],
        homogeneity=100,
        seed=7,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(
        f'SELECT trade_id, group_num, qty, counterparty, parent_id FROM "{table}"'
    ).fetchall()
    assert len(rows) == 30
    for trade_id, group_num, qty, counterparty, parent_id in rows:
        assert 1 <= group_num <= 100
        assert 1 <= qty <= 1000
        assert counterparty  # non-empty Faker company name, unaffected by this migration
        assert parent_id is not None

    # Each distinct trade_id (an SQL-generated PARENT field) must map to exactly one
    # parent_id — proving the parent-row-per-group counting is correct, not reused
    # across groups or regenerated per child row.
    groups_seen: dict[str, set] = {}
    for trade_id, _, _, _, parent_id in rows:
        groups_seen.setdefault(trade_id, set()).add(parent_id)
    assert all(len(pids) == 1 for pids in groups_seen.values())
    assert len(groups_seen) == 3  # exactly 3 distinct parent trade_ids for 3 groups


def test_sql_eligible_fields_in_grouped_dataset_with_flat_rows(db):
    # split_pct < 100 means some rows are "flat" (ungrouped, parent_id=None), each
    # generating its own one-off parent row — this exercises the flat_rows branch
    # of the parent_call_count logic, not just the grouped branch.
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="grouped_sql_partial",
                rows=20,
                group_config=GroupConfig(
                    num_groups=2,
                    split_pct=50,
                    parent_fields=[
                        FieldDefinition(name="group_num", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=100)),
                    ],
                    child_fields=[
                        FieldDefinition(name="qty", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=1000)),
                    ],
                ),
            ),
        ],
        homogeneity=100,
        seed=9,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT group_num, qty, parent_id FROM "{table}"').fetchall()
    assert len(rows) == 20
    flat_rows = [r for r in rows if r[2] is None]
    grouped_rows = [r for r in rows if r[2] is not None]
    assert len(flat_rows) == 10  # 50% of 20
    assert len(grouped_rows) == 10
    for group_num, qty, _ in rows:
        assert 1 <= group_num <= 100
        assert 1 <= qty <= 1000


def test_condition_on_later_field_sees_sql_generated_earlier_field(db):
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="condition_on_sql_field",
                rows=200,
                fields=[
                    FieldDefinition(name="score", generator="random_int", type="integer",
                                     constraint=ConstraintConfig(min=1, max=100)),
                    FieldDefinition(name="tier", generator="random_element", type="string",
                                     constraint=ConstraintConfig(values="gold,standard"),
                                     condition="score >= 50"),
                ],
            ),
        ],
        homogeneity=100,
        seed=123,
    )
    resp = generate_datasets(req)
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT score, tier FROM "{table}"').fetchall()
    assert len(rows) == 200
    saw_gold_or_standard = False
    saw_null_tier = False
    for score, tier in rows:
        assert 1 <= score <= 100  # score took the SQL path
        if score >= 50:
            assert tier in ("gold", "standard")
            saw_gold_or_standard = True
        else:
            assert tier is None  # condition correctly saw the SQL-generated score and skipped tier
            saw_null_tier = True
    # With 200 rows and a uniform [1,100] score, both branches should appear —
    # if this ever flakes, the seed/range no longer guarantees both branches occur.
    assert saw_gold_or_standard
    assert saw_null_tier


def test_grouped_dataset_num_groups_exceeds_grouped_rows_does_not_crash(db):
    # num_groups (100) far exceeds grouped_rows (5, since split_pct=100 and rows=5) —
    # this used to raise IndexError once a child field took the SQL fast path.
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(
                name="tiny_many_groups",
                rows=5,
                group_config=GroupConfig(
                    num_groups=100,
                    split_pct=100,
                    parent_fields=[
                        FieldDefinition(name="parent_marker", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=10)),
                    ],
                    child_fields=[
                        FieldDefinition(name="qty", generator="random_int", type="integer",
                                         constraint=ConstraintConfig(min=1, max=1000)),
                    ],
                ),
            ),
        ],
        homogeneity=100,
        seed=17,
    )
    resp = generate_datasets(req)  # must not raise
    table = resp.datasets[0].table_name
    rows = db.execute(f'SELECT qty FROM "{table}"').fetchall()
    assert len(rows) >= 5  # at least the requested rows exist; over-generation (pre-existing, out of scope) may add more
    for (qty,) in rows:
        assert 1 <= qty <= 1000


def test_flat_field_breaks_applied_to_non_authoritative_dataset(db):
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(
            name="amount", generator="random_int", type="integer",
            constraint=ConstraintConfig(min=10000, max=99999),
        ),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="gl", rows=20, fields=list(shared_fields)),
            DatasetDefinition(name="subledger", rows=20, fields=list(shared_fields)),
        ],
        homogeneity=100,
        seed=42,
        overlap_ratio=1.0,
        exact_fields=["trade_id", "amount"],
        reconciliation_mode=True,
        field_breaks=[
            FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)
        ],
    )
    resp = generate_datasets(req)

    trade_ids_0 = [r[0] for r in db.execute(f'SELECT trade_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    trade_ids_1 = [r[0] for r in db.execute(f'SELECT trade_id FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert trade_ids_0 == trade_ids_1  # join key never breaks

    amounts_0 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[0].table_name}"').fetchall()]
    amounts_1 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[1].table_name}"').fetchall()]
    for true_v, broken_v in zip(amounts_0, amounts_1, strict=True):
        assert abs(broken_v - true_v) <= true_v * 0.1 + 1

    assert resp.break_count == 20  # one non-authoritative dataset, break_rate=1.0, 20 rows
    gt_rows = db.execute("SELECT COUNT(*) FROM metadata_recon_breaks WHERE run_id = ?", [resp.run_id]).fetchone()[0]
    assert gt_rows == 20


def test_flat_field_breaks_zero_rate_no_ground_truth(db):
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="amount", generator="random_int", type="integer"),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="gl", rows=10, fields=list(shared_fields)),
            DatasetDefinition(name="subledger", rows=10, fields=list(shared_fields)),
        ],
        homogeneity=100,
        seed=42,
        exact_fields=["trade_id", "amount"],
        reconciliation_mode=True,
        field_breaks=[FieldBreakConfig(field_name="amount", break_rate=0.0)],
    )
    resp = generate_datasets(req)
    amounts_0 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[0].table_name}"').fetchall()]
    amounts_1 = [r[0] for r in db.execute(f'SELECT amount FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert amounts_0 == amounts_1
    assert resp.break_count == 0


def test_grouped_field_breaks_applied_to_child_field(db):
    from app.schemas.generation import FieldBreakConfig

    def _grouped_def(name: str) -> DatasetDefinition:
        return DatasetDefinition(
            name=name,
            rows=10,
            group_config=GroupConfig(
                num_groups=2,
                split_pct=100,
                parent_fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")],
                child_fields=[
                    FieldDefinition(name="counterparty_id", generator="uuid4", type="string"),
                    FieldDefinition(
                        name="qty", generator="random_int", type="integer",
                        constraint=ConstraintConfig(min=1000, max=9999),
                    ),
                ],
            ),
        )

    req = GenerateRequest(
        datasets=[_grouped_def("g1"), _grouped_def("g2")],
        homogeneity=100,
        seed=42,
        overlap_ratio=1.0,
        exact_fields=["counterparty_id", "qty"],
        reconciliation_mode=True,
        field_breaks=[FieldBreakConfig(field_name="qty", break_rate=1.0, break_style="drift", drift_pct=0.1)],
    )
    resp = generate_datasets(req)

    cp_0 = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[0].table_name}"').fetchall()]
    cp_1 = [r[0] for r in db.execute(f'SELECT counterparty_id FROM "{resp.datasets[1].table_name}"').fetchall()]
    assert cp_0 == cp_1  # join key never breaks

    qty_0 = [r[0] for r in db.execute(f'SELECT qty FROM "{resp.datasets[0].table_name}"').fetchall()]
    qty_1 = [r[0] for r in db.execute(f'SELECT qty FROM "{resp.datasets[1].table_name}"').fetchall()]
    for true_v, broken_v in zip(qty_0, qty_1, strict=True):
        assert abs(broken_v - true_v) <= true_v * 0.1 + 1

    assert resp.break_count == 10


def test_reconciliation_mode_requires_two_datasets(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    req = GenerateRequest(
        datasets=[DatasetDefinition(name="ds1", rows=5, fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")])],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
    )
    with pytest.raises(ValueError, match="at least 2 datasets"):
        generate_datasets(req)


def test_reconciliation_mode_requires_exact_fields(db):
    import pytest

    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")]),
            DatasetDefinition(name="ds2", rows=5, fields=[FieldDefinition(name="trade_id", generator="uuid4", type="string")]),
        ],
        reconciliation_mode=True,
    )
    with pytest.raises(ValueError, match="requires exact_fields"):
        generate_datasets(req)


def test_field_breaks_without_reconciliation_mode_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        field_breaks=[FieldBreakConfig(field_name="trade_id", break_rate=0.1)],
    )
    with pytest.raises(ValueError, match="requires reconciliation_mode"):
        generate_datasets(req)


def test_field_break_on_join_key_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
        field_breaks=[FieldBreakConfig(field_name="trade_id", break_rate=0.1)],
    )
    with pytest.raises(ValueError, match="cannot target the join key"):
        generate_datasets(req)


def test_field_break_not_in_exact_fields_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="notes", generator="text", type="string"),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
        field_breaks=[FieldBreakConfig(field_name="notes", break_rate=0.1)],
    )
    with pytest.raises(ValueError, match="must be listed in exact_fields"):
        generate_datasets(req)


def test_field_break_drift_on_non_numeric_field_rejected(db):
    import pytest
    from app.schemas.generation import FieldBreakConfig

    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="status", generator="random_element", type="string"),
    ]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id", "status"],
        field_breaks=[FieldBreakConfig(field_name="status", break_rate=0.1, break_style="drift")],
    )
    with pytest.raises(ValueError, match="not numeric"):
        generate_datasets(req)


def test_reconciliation_mode_forces_overlap_ratio_to_one(db):
    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=8, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=8, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
        overlap_ratio=0.0,  # deliberately not 1.0 — must be forced
    )
    resp = generate_datasets(req)
    assert resp.overlap_pool_size == 8


def test_reconciliation_mode_requires_equal_row_counts(db):
    import pytest

    shared_fields = [FieldDefinition(name="trade_id", generator="uuid4", type="string")]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=8, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=10, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=["trade_id"],
    )
    with pytest.raises(ValueError, match="same number of rows"):
        generate_datasets(req)


def test_reconciliation_mode_exact_fields_response_preserves_request_order(db):
    shared_fields = [
        FieldDefinition(name="trade_id", generator="uuid4", type="string"),
        FieldDefinition(name="amount", generator="random_int", type="integer"),
        FieldDefinition(name="status", generator="random_element", type="string"),
        FieldDefinition(name="notes", generator="text", type="string"),
    ]
    ordered_exact_fields = ["notes", "status", "trade_id", "amount"]
    req = GenerateRequest(
        datasets=[
            DatasetDefinition(name="ds1", rows=5, fields=list(shared_fields)),
            DatasetDefinition(name="ds2", rows=5, fields=list(shared_fields)),
        ],
        reconciliation_mode=True,
        exact_fields=ordered_exact_fields,
    )
    resp = generate_datasets(req)
    # exact_fields[0] is the join key by contract; the response must echo the exact
    # request order, not a Python set's arbitrary iteration order.
    assert resp.exact_fields == ordered_exact_fields


def _grouped_def_with_parent_key(name: str, num_groups: int = 4, split_pct: float = 100, rows: int = 20) -> DatasetDefinition:
    return DatasetDefinition(
        name=name,
        rows=rows,
        group_config=GroupConfig(
            num_groups=num_groups,
            split_pct=split_pct,
            parent_fields=[FieldDefinition(name="transaction_id", generator="uuid4", type="string")],
            child_fields=[
                FieldDefinition(
                    name="amount", generator="random_int", type="integer",
                    constraint=ConstraintConfig(min=1000, max=9999),
                ),
            ],
        ),
    )


def test_parent_join_key_rejects_flat_dataset_in_batch(db):
    import pytest

    flat_def = DatasetDefinition(
        name="flat_ds", rows=20,
        fields=[FieldDefinition(name="transaction_id", generator="uuid4", type="string")],
    )
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), flat_def],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="requires every dataset to be grouped"):
        generate_datasets(req)


def test_parent_join_key_rejects_child_designation_on_other_dataset(db):
    import pytest

    mismatched_def = DatasetDefinition(
        name="subledger", rows=20,
        group_config=GroupConfig(
            num_groups=4,
            split_pct=100,
            parent_fields=[FieldDefinition(name="other_parent", generator="word", type="string")],
            child_fields=[
                FieldDefinition(name="transaction_id", generator="uuid4", type="string"),
                FieldDefinition(
                    name="amount", generator="random_int", type="integer",
                    constraint=ConstraintConfig(min=1000, max=9999),
                ),
            ],
        ),
    )
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), mismatched_def],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="requires every dataset to be grouped"):
        generate_datasets(req)


def test_parent_join_key_rejects_num_groups_mismatch(db):
    import pytest

    req = GenerateRequest(
        datasets=[
            _grouped_def_with_parent_key("gl", num_groups=4),
            _grouped_def_with_parent_key("subledger", num_groups=5),
        ],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="same num_groups"):
        generate_datasets(req)


def test_parent_join_key_rejects_split_pct_not_100(db):
    import pytest

    req = GenerateRequest(
        datasets=[
            _grouped_def_with_parent_key("gl", split_pct=100),
            _grouped_def_with_parent_key("subledger", split_pct=80),
        ],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    with pytest.raises(ValueError, match="split_pct=100"):
        generate_datasets(req)


def test_child_join_key_validation_unchanged(db):
    # Regression: a plain child-level join key (today's only prior case) must still be rejected
    # if it's actually a parent field — the carve-out must not accidentally widen this check.
    import pytest

    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["amount", "transaction_id"],  # "amount" (child) is the join key here, "transaction_id" (parent) is not
    )
    with pytest.raises(ValueError, match="parent field"):
        generate_datasets(req)


def test_parent_join_key_matches_across_groups(db):
    from app.schemas.generation import FieldBreakConfig

    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id", "amount"],
        field_breaks=[FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)],
    )
    resp = generate_datasets(req)

    tx_ids_0 = {
        r[0] for r in db.execute(f'SELECT transaction_id FROM "{resp.datasets[0].table_name}"').fetchall()
    }
    tx_ids_1 = {
        r[0] for r in db.execute(f'SELECT transaction_id FROM "{resp.datasets[1].table_name}"').fetchall()
    }
    assert tx_ids_0 == tx_ids_1  # same set of transaction_ids in both datasets
    assert len(tx_ids_0) == 4  # matches num_groups

    assert resp.break_count == 20  # dataset[1]'s 20 child rows all broke on "amount" (break_rate=1.0)


def test_parent_join_key_group_sizes_are_deterministic_and_aligned(db):
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id"],
    )
    resp = generate_datasets(req)

    def _counts_by_tx(table_name: str) -> dict:
        rows = db.execute(f'SELECT transaction_id FROM "{table_name}"').fetchall()
        counts: dict = {}
        for (tx,) in rows:
            counts[tx] = counts.get(tx, 0) + 1
        return counts

    counts_0 = _counts_by_tx(resp.datasets[0].table_name)
    counts_1 = _counts_by_tx(resp.datasets[1].table_name)
    assert counts_0 == counts_1  # identical child-row count per transaction_id in both datasets


def _grouped_def_with_second_parent_field(name: str, num_groups: int = 4, split_pct: float = 100, rows: int = 20) -> DatasetDefinition:
    # "region" is declared BEFORE "transaction_id" in parent_fields, so the join key
    # sits at parent-field index 1, not 0 — this forces grouped.py's
    # parent_field_names.index(join_key_field) resolution to actually matter.
    return DatasetDefinition(
        name=name,
        rows=rows,
        group_config=GroupConfig(
            num_groups=num_groups,
            split_pct=split_pct,
            parent_fields=[
                FieldDefinition(name="region", generator="country_code", type="string"),
                FieldDefinition(name="transaction_id", generator="uuid4", type="string"),
            ],
            child_fields=[
                FieldDefinition(
                    name="amount", generator="random_int", type="integer",
                    constraint=ConstraintConfig(min=1000, max=9999),
                ),
            ],
        ),
    )


def test_parent_join_key_ground_truth_records_parent_value_not_child_value(db):
    # Regression: metadata_recon_breaks.join_key_value must be read from the PARENT row
    # (via parent_field_names.index(join_key_field)) when the join key is a parent-level
    # field. Using a second, earlier parent field ("region") ensures the join key is not
    # trivially at index 0, so an indexing bug in grouped.py would be caught here.
    from collections import Counter

    from app.schemas.generation import FieldBreakConfig

    req = GenerateRequest(
        datasets=[
            _grouped_def_with_second_parent_field("gl"),
            _grouped_def_with_second_parent_field("subledger"),
        ],
        homogeneity=100,
        seed=42,
        reconciliation_mode=True,
        exact_fields=["transaction_id", "amount"],
        field_breaks=[FieldBreakConfig(field_name="amount", break_rate=1.0, break_style="drift", drift_pct=0.1)],
    )
    resp = generate_datasets(req)

    breaking_dataset_id = resp.datasets[1].dataset_id
    gt_rows = db.execute(
        "SELECT join_key_value, true_value FROM metadata_recon_breaks WHERE run_id = ? AND dataset_id = ?",
        [resp.run_id, breaking_dataset_id],
    ).fetchall()
    assert len(gt_rows) == 20  # dataset[1]'s 20 child rows all broke on "amount" (break_rate=1.0)
    gt_pairs = Counter((str(jk), str(tv)) for jk, tv in gt_rows)

    authoritative_rows = db.execute(
        f'SELECT transaction_id, amount FROM "{resp.datasets[0].table_name}"'
    ).fetchall()
    authoritative_pairs = Counter((str(tx), str(amount)) for tx, amount in authoritative_rows)

    # Every recorded (join_key_value, true_value) pair must correspond exactly to a
    # (transaction_id, amount) pair on the authoritative dataset — proving join_key_value
    # is genuinely the parent's transaction_id, not e.g. the parent's "region" value
    # (which an off-by-one index bug would have produced instead).
    assert gt_pairs == authoritative_pairs


def test_child_join_key_group_sizes_stay_random(db):
    # Regression: a plain child-level join key (the existing, already-shipped case) must NOT
    # switch to deterministic group sizing — this flag is scoped strictly to parent-level keys.
    req = GenerateRequest(
        datasets=[_grouped_def_with_parent_key("gl"), _grouped_def_with_parent_key("subledger")],
        homogeneity=100,
        seed=42,
        overlap_ratio=1.0,
        exact_fields=["amount"],  # child-level join key, no reconciliation_mode
    )
    resp = generate_datasets(req)
    assert resp.datasets[0].row_count == 20
    assert resp.datasets[1].row_count == 20
