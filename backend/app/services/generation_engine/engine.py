from __future__ import annotations

import random

from faker import Faker

from app.core.database import DuckDBManager
from app.schemas.generation import DatasetResult, GenerateRequest, GenerateResponse
from app.services.generation_engine.flat import generate_dataset
from app.services.generation_engine.grouped import generate_grouped_dataset
from app.services.generation_engine.overlap import build_overlap_pool, effective_fields


def generate_datasets(request: GenerateRequest) -> GenerateResponse:
    master_seed = request.seed if request.seed is not None else random.randint(0, 2**31 - 1)
    main_fake = Faker()
    main_fake.seed_instance(master_seed)
    random.seed(master_seed)

    # Validate overlap config before touching DuckDB
    overlap_ratio = request.overlap_ratio
    exact_field_names = set(request.exact_fields)
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

    dataset_results: list[DatasetResult] = []
    for dataset_def in request.datasets:
        if dataset_def.group_config:
            dr = generate_grouped_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
            )
        else:
            dr = generate_dataset(
                fake=main_fake,
                definition=dataset_def,
                run_id=run_id,
                homogeneity=request.homogeneity,
                master_seed=master_seed,
                overlap_pool=overlap_pool,
            )
        dataset_results.append(dr)

    return GenerateResponse(
        run_id=run_id,
        homogeneity=request.homogeneity,
        seed=master_seed,
        datasets=dataset_results,
        overlap_pool_size=pool_size,
        exact_fields=list(exact_field_names),
    )
