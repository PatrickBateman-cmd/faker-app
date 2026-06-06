# Rust Generation Engine Migration

Port the Faker-based generation hot path from Python to Rust via PyO3 for 4–6× throughput on multi-core machines.

---

## Why

| Metric | Python (current) | Rust (target) |
|---|---|---|
| 100K rows × 15 fields | ~3–5s (GIL-bound) | ~0.5–1s (all cores) |
| Overhead per 1.5M Faker calls | ~2µs (Python object overhead) | ~0.3µs (native struct) |
| Parallelism | `multiprocessing` (pickle overhead) | `rayon` (zero-copy work-stealing) |

**The generation engine is the only CPU-bound hot path** — everything else (DuckDB, HTTP, yfinance) is I/O-bound and fast enough in Python.

---

## Architecture

```
Before:                           After:
┌────────────────────┐            ┌────────────────────┐
│  generation_engine │            │  generation_engine │
│  (Python)          │   ───→    │  (Python stub)     │
│                    │            │                    │
│  generate_datasets │            │  generate_datasets │
│  _generate_dataset │            │  _generate_dataset │
│  _generate_field   │            │  import faker_engine│
│  _apply_constraint │            │  faker_engine.gen()│
└────────────────────┘            └──────┬─────────────┘
                                         │ PyO3
                                         ▼
                                ┌────────────────────┐
                                │  faker_engine.so    │
                                │  (Rust crate)       │
                                │                     │
                                │  - gen_rows() →     │
                                │    Vec<Vec<String>>  │
                                │  - rayon::par_iter() │
                                │  - fake crate        │
                                │  - rand_chacha seeds │
                                └────────────────────┘
```

### What moves to Rust vs stays in Python

| Code | Stays | Moves | Reason |
|---|---|---|---|
| `generate_datasets()` | ✅ | | DuckDB metadata inserts, run_id sequencing |
| `_generate_dataset()` | ✅ | | DuckDB table creation, metadata registration |
| `_generate_field_value()` | | ✅ | Hot loop — 1.5M calls for 100K × 15 fields |
| `_apply_constraint()` | | ✅ | Called per value, Rust avoids Python overhead |
| `_infer_duckdb_types()` | ✅ | | Trivial type map, called once per dataset |
| Row loop + `executemany()` | ✅ | | DuckDB Python binding is already native C++ |

---

## File Map

```
backend/
├── Cargo.toml                  ← NEW
├── pyproject.toml              ← add [tool.maturin]
├── src/
│   ├── lib.rs                  ← NEW: PyO3 entry, gen_rows()
│   └── generators.rs           ← NEW: 28 generator functions
├── app/services/
│   └── generation_engine.py    ← MODIFIED: replaces inner loop
└── requirements.txt            ← add maturin
```

---

## Cargo.toml

```toml
[package]
name = "faker-engine"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
fake = { version = "2.9", features = ["datetime"] }
rand = "0.8"
rand_chacha = "0.3"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
rayon = "1.8"
uuid = { version = "1", features = ["v4"] }
chrono = "0.4"
```

---

## Generator Map (Python Faker → Rust `fake` + `rand`)

| generator | Python Faker | Rust | Deterministic? |
|---|---|---|---|
| `first_name` | `fake.first_name()` | `fake::faker::name::raw::FirstName(rng)` | ✅ seeded |
| `last_name` | `fake.last_name()` | `fake::faker::name::raw::LastName(rng)` | ✅ |
| `name` | `fake.name()` | `fake::faker::name::raw::Name(rng)` | ✅ |
| `email` | `fake.email()` | `fake::faker::internet::raw::FreeEmail(rng)` | ✅ |
| `phone_number` | `fake.phone_number()` | `fake::faker::phone_number::raw::PhoneNumber(rng)` | ✅ |
| `job` | `fake.job()` | `fake::faker::job::raw::Title(rng)` | ✅ |
| `company` | `fake.company()` | `fake::faker::company::raw::CompanyName(rng)` | ✅ |
| `catch_phrase` | `fake.catch_phrase()` | `fake::faker::company::raw::CatchPhase(rng)` | ✅ |
| `domain_name` | `fake.domain_name()` | `fake::faker::internet::raw::DomainSuffix(rng)` | ✅ |
| `url` | `fake.url()` | `format!("https://{}.com", domain)` | ✅ |
| `country` | `fake.country()` | `fake::faker::address::raw::Country(rng)` | ✅ |
| `country_code` | `fake.country_code()` | `fake::faker::address::raw::CountryCode(rng)` | ✅ |
| `city` | `fake.city()` | `fake::faker::address::raw::CityName(rng)` | ✅ |
| `street_address` | `fake.street_address()` | `fake::faker::address::raw::StreetName(rng)` | ✅ |
| `zipcode` | `fake.zipcode()` | `fake::faker::address::raw::ZipCode(rng)` | ✅ |
| `text` | `fake.text(max_nb_chars=N)` | `fake::faker::lorem::raw::Sentence(rng, ..)` truncated | ✅ |
| `boolean` | `fake.boolean()` | `rng.gen_bool(0.5)` | ✅ |
| `random_int` | `fake.random_int(min, max)` | `rng.gen_range(min..=max)` | ✅ |
| `pydecimal` | `fake.pydecimal(...)` | `rng.gen_range(low..high)` rounded | ✅ |
| `uuid4` | `str(uuid.uuid4())` | `Uuid::new_v4().to_string()` | ✅ |
| `uuid_int` | `uuid.uuid4().int & ((1<<63)-1)` | `Uuid::new_v4().as_u128() as i64` | ✅ |
| `bothify` | `fake.bothify("???###")` | Custom: letter? replace, hash? replace | ✅ |
| `random_element` | `fake.random_element(vals)` | `vals.choose(rng)` | ✅ |
| `currency_code` | `fake.currency_code()` | `CODES.choose(rng)` (static list) | ✅ |
| `swift` | `fake.swift8()` | Custom: 8 alphanum using `rand` | ✅ |
| `iban` | `fake.iban()` | Custom: country + 2 check digits + alphanum | ✅ |
| `bban` | `fake.bban()` | Custom: 11 alphanum characters | ✅ |
| `date_between` | `fake.date_between(start, end)` | `rng.gen_range(start..end).isoformat()` | ✅ |
| `date_of_birth` | `fake.date_of_birth(min,max_age)` | `now - years`, random day | ✅ |
| `date_time` | `fake.date_time()` | `rng.gen_range(epoch..now).isoformat()` | ✅ |
| `word` | `fake.word()` | `fake::faker::lorem::raw::Word(rng)` | ✅ |

> **Note:** Rust `fake` uses different word lists than Python `Faker`. Same seed → same Rust output, but differs from Python output. This is acceptable — the data is structurally valid, not byte-for-byte reproducible across languages.

---

## Rust Core: `gen_rows()` (PyO3)

```rust
#[pyfunction]
fn gen_rows(
    master_seed: u64,
    homogeneity: u8,
    field_defs: Vec<String>,       // JSON: Vec<FieldDef>
    shared_key_pool: Option<Vec<String>>,
    row_count: u32,
) -> PyResult<Vec<Vec<String>>> {
    let fields: Vec<FieldDef> = field_defs
        .iter()
        .map(|s| serde_json::from_str(s).map_err(|e| PyErr::from(e)))
        .collect::<PyResult<_>>()?;

    // Pre-compute per-field RNGs (homogeneity logic)
    let mut rng = rand_chacha::ChaCha8Rng::seed_from_u64(master_seed);
    let pool = shared_key_pool.unwrap_or_default();
    let seeds: Vec<Option<u64>> = fields.iter().map(|f| {
        if f.is_shared_key_or_formula() {
            None
        } else if rng.gen_range(1..=100) <= homogeneity {
            Some((master_seed.wrapping_mul(31).wrapping_add(hash(&f.name))) % 10u64.pow(9))
        } else {
            None  // will use per-row advancing RNG
        }
    }).collect();

    let pool_ref = &pool;
    let fields_ref = &fields;
    let seeds_ref = &seeds;

    // Parallel: chunk rows across cores
    let rows: Vec<Vec<String>> = (0..row_count)
        .into_par_iter()
        .map(|_| {
            let mut row_rng = rand::rngs::SmallRng::from_entropy();
            let mut row = Vec::with_capacity(fields_ref.len());
            for (i, field) in fields_ref.iter().enumerate() {
                let val = match field.generator.as_str() {
                    "shared_key" => pool_ref.choose(&mut row_rng)
                        .cloned().unwrap_or_default(),
                    "formula" => field.formula.clone().unwrap_or_default(),
                    _ => {
                        let mut rng: Box<dyn RngCore> = match seeds_ref[i] {
                            Some(s) => Box::new(rand_chacha::ChaCha8Rng::seed_from_u64(s)),
                            None => Box::new(&mut row_rng),
                        };
                        generate_value(field, &mut *rng)
                    }
                };
                row.push(val);
            }
            row
        })
        .collect();

    Ok(rows)
}
```

---

## Homogeneity Logic (replicated in Rust)

Same algorithm as Python:
1. For each non-special field, roll `rng.gen_range(1..=100)`
2. If `roll <= homogeneity` → create a **dedicated seeded RNG** `ChaCha8Rng::seed_from_u64(field_seed)` — this field produces the same value every row
3. If `roll > homogeneity` → no dedicated RNG, uses a per-row ephemeral `SmallRng::from_entropy()` — produces different values per row

Result: at 100% homogeneity, every field gets a dedicated RNG → identical values in every row. At 1%, nearly all fields randomize per row.

---

## Python Integration

```python
# generation_engine.py — modified _generate_dataset()

from faker_engine import gen_rows

def _generate_dataset(fake, definition, run_id, homogeneity, master_seed):
    # ... table creation (unchanged) ...
    # ... shared_key_pool loading (unchanged) ...

    field_defs_json = [
        f.model_dump_json() for f in fields
    ]

    result_rows = gen_rows(
        master_seed=master_seed,
        homogeneity=homogeneity,
        field_defs=field_defs_json,
        shared_key_pool=shared_key_pool,
        row_count=rows,
    )

    # Insert via DuckDB executemany (unchanged)
    db.get_connection().executemany(insert_sql, result_rows)

    # ... metadata insert (unchanged) ...
```

---

## Build Commands

```sh
# One-time: install Rust toolchain
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Development build (links into venv)
cd backend
maturin develop

# Production build
maturin build --release
pip install target/wheels/faker_engine-*.whl

# Run benchmark
uv run python -c "
from app.services.generation_engine import generate_datasets
from app.schemas.generation import GenerateRequest, DatasetDefinition, FieldDefinition
import time

req = GenerateRequest(
    datasets=[DatasetDefinition(
        name='bench',
        rows=100000,
        fields=[FieldDefinition(name=f'col{i}', generator='name', type='string') for i in range(15)]
    )],
    homogeneity=100,
    seed=42,
)
start = time.time()
resp = generate_datasets(req)
print(f'100K rows × 15 fields: {time.time() - start:.2f}s')
"
```

---

## Implementation Order

| Step | What | Files | Est. |
|---|---|---|---|
| **1** | Scaffold: `maturin init`, Cargo.toml, PyO3 entry, build test | `Cargo.toml`, `src/lib.rs`, `pyproject.toml` | 30m |
| **2** | Constraint + type structs | `src/lib.rs` (+50 lines) | 15m |
| **3** | 28 generators using `fake` + `rand` | `src/generators.rs` (+200 lines) | 90m |
| **4** | `gen_rows()`: parse JSON, seed RNGs, parallel loop | `src/lib.rs` (+120 lines) | 60m |
| **5** | Modify `generation_engine.py` — swap inner loop | `generation_engine.py` (~20 lines) | 15m |
| **6** | Integration test + benchmark | Manual | 30m |
| | **Total** | | **~4h** |

---

## Rollback Plan

If the Rust build fails or produces incorrect output:

```sh
git checkout -- backend/app/services/generation_engine.py
pip uninstall faker-engine
maturin build fails → Python generation_engine is unchanged, app continues working. The Rust module is only called from the modified generation_engine.py, so reverting that file fully restores the Python path.
```
