from __future__ import annotations

import random

from faker import Faker

from app.core.database import DuckDBManager
from app.schemas.generation import DatasetResult, FieldBreakConfig, GenerateRequest, GenerateResponse
from app.services.generation_engine.breaks import BreakRecord
from app.services.generation_engine.flat import generate_dataset
from app.services.generation_engine.grouped import generate_grouped_dataset
from app.services.generation_engine.overlap import build_overlap_pool, effective_fields
from app.services.generation_engine.persistence import persist_recon_breaks

_NUMERIC_TYPES = {"integer", "int", "float", "decimal", "number"}


def generate_datasets(request: GenerateRequest) -> GenerateResponse:
    master_seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
    main_fake = Faker()
    main_fake.seed_instance(master_seed)
    random.seed(master_seed)

    overlap_ratio = request.overlap_ratio
    exact_field_names = set(request.exact_fields)

    join_key_field: str | None = None
    field_breaks_by_name: dict[str, FieldBreakConfig] = {}
    if request.reconciliation_mode:
        if len(request.datasets) < 2:
            raise ValueError("reconciliation_mode requires at least 2 datasets")
        if not request.exact_fields:
            raise ValueError("reconciliation_mode requires exact_fields (join key first)")
        if len({ds.rows for ds in request.datasets}) > 1:
            raise ValueError("reconciliation_mode requires all datasets to declare the same number of rows")
        overlap_ratio = 1.0
        join_key_field = request.exact_fields[0]
        for fb in request.field_breaks:
            if fb.field_name not in exact_field_names:
                raise ValueError(f"field_breaks field '{fb.field_name}' must be listed in exact_fields")
            if fb.field_name == join_key_field:
                raise ValueError(f"field_breaks cannot target the join key field '{join_key_field}'")
            if fb.break_style == "drift":
                for ds in request.datasets:
                    target = next((f for f in effective_fields(ds) if f.name == fb.field_name), None)
                    if target is not None and target.type.lower() not in _NUMERIC_TYPES:
                        raise ValueError(
                            f"field_breaks '{fb.field_name}' uses break_style='drift' but field type "
                            f"'{target.type}' is not numeric in dataset '{ds.name}'"
                        )
            field_breaks_by_name[fb.field_name] = fb
    elif request.field_breaks:
        raise ValueError("field_breaks requires reconciliation_mode=True")

    # Validate overlap config before touching DuckDB
    if overlap_ratio > 0:
        if not exact_field_names:
            raise ValueError("exact_fields must be specified when overlap_ratio > 0")
        for ds in request.datasets:
            if ds.group_config:
                parent_names = {f.name for f in ds.group_config.parent_fields}
                for ef in exact_field_names:
                    if ef in parent_names:
                        raise ValueError(
                            f"exact field '{ef}' is a parent field in grouped dataset '{ds.name}'; "
                            "overlap only supports child-level fields for grouped datasets"
                        )
            ds_field_names = {f.name for f in effective_fields(ds)}
            for ef in exact_field_names:
                if ef not in ds_field_names:
                    raise ValueError(f"exact field '{ef}' not found in dataset '{ds.name}'")

    db = DuckDBManager.get_instance()
    result = db.execute("SELECT nextval('seq_run_id')").fetchone()
    run_id = result[0] if result else 1

    # Build the global overlap pool once
    overlap_pool: list[dict] = []
    pool_size = 0
    if overlap_ratio > 0 and request.datasets:
        pool_size = int(min(d.rows for d in request.datasets) * overlap_ratio)
        if pool_size > 0:
            first_fields = effective_fields(request.datasets[0])
            overlap_pool = build_overlap_pool(main_fake, first_fields, exact_field_names, pool_size)

    ground_truth: list[BreakRecord] = []
    dataset_results: list[DatasetResult] = []
    for idx, dataset_def in enumerate(request.datasets):
        ds_field_breaks = field_breaks_by_name if idx > 0 else {}
        if dataset_def.group_config:
            dr = generate_grouped_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
                exact_field_names=exact_field_names,
                join_key_field=join_key_field,
                field_breaks=ds_field_breaks,
                ground_truth=ground_truth,
            )
        else:
            dr = generate_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
                exact_field_names=exact_field_names,
                join_key_field=join_key_field,
                field_breaks=ds_field_breaks,
                ground_truth=ground_truth,
            )
        dataset_results.append(dr)

    if ground_truth:
        persist_recon_breaks(db, run_id, ground_truth)

    return GenerateResponse(
        run_id=run_id,
        homogeneity=request.homogeneity,
        seed=master_seed,
        datasets=dataset_results,
        overlap_pool_size=pool_size,
        exact_fields=request.exact_fields,
        break_count=len(ground_truth),
    )
