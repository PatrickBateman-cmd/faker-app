# Architecture Diagrams

## 1. System Architecture

High-level component view — how the three client interfaces connect through to storage and external APIs.

```mermaid
flowchart TB
    subgraph clients["Client Interfaces"]
        browser["Browser\nReact 19 · TanStack Query · Recharts"]
        cli["CLI\nTyper · Rich"]
        tui["TUI\nTextual (6 screens)"]
    end

    subgraph frontend["Frontend  :5173"]
        vite["Vite Dev Server\n/api/* → strip prefix → :8000"]
    end

    subgraph backend["FastAPI Backend  :8000"]
        mw["CORS Middleware\n+ Global Exception Handler"]

        subgraph routers["Routers  (HTTP boundary — thin layer only)"]
            direction LR
            r_gen["generation\nPOST /generate"]
            r_ds["datasets\nGET · PATCH · DELETE"]
            r_exp["exports\nGET /export/csv|parquet|xlsx|jsonl"]
            r_agg["aggregation\nPOST /aggregate  /dedup"]
            r_tmpl["templates\nCRUD /templates"]
            r_iso["iso20022\n/domains · /search · /xsd · /save-template"]
            r_fin["financial\n/quote · /history · /batch · /enrich"]
            r_kg["kaggle\n/credentials · /search · /files · /import"]
        end

        subgraph services["Services  (all business logic lives here)"]
            direction LR
            s_gen["generation_engine"]
            s_ds["dataset_service"]
            s_exp["export_service"]
            s_tf["transform_service\n(aggregate + dedup)"]
            s_tmpl["template_library"]
            s_iso["iso20022_service"]
            s_fin["financial_service"]
            s_kg["kaggle_service"]
        end

        subgraph core["Core"]
            dbmgr["DuckDBManager\nRLock · transaction()"]
            valid["validation.py\ntable & column name guards"]
            mig["migrations.py\n6 versioned migrations"]
        end
    end

    subgraph storage["Storage"]
        duckdb[("DuckDB\ndefault_user.duckdb")]
        xml["XML Templates\napp/templates/*.xml  (13 files)"]
        tmpdir["OS temp\n/tmp/faker_exports/token_hex.ext"]
    end

    subgraph external["External APIs"]
        kaggle_api["Kaggle API\nkaggle SDK · KGAT bearer token"]
        yfinance_api["Yahoo Finance\nyfinance · LRU TTL cache"]
        iso_org["iso20022.org\nXSD catalog · host-allowlisted"]
    end

    browser -->|"HTTP  /api/*"| vite
    vite -->|"strips /api prefix"| mw
    cli -->|"direct in-process"| services
    tui -->|"direct in-process\n(stop server first — single-writer)"| services

    mw --> routers
    routers --> services
    services --> core
    core --> duckdb

    s_tmpl -->|"read / write"| xml
    s_exp -->|"write temp file"| tmpdir
    s_kg -->|"download CSV"| kaggle_api
    s_fin -->|"quote · history"| yfinance_api
    s_iso -->|"scrape XSD"| iso_org
```

---

## 2. Data Flows

### 2a. Dataset Generation Pipeline

```mermaid
flowchart TD
    A["POST /generate\nbody: {datasets, homogeneity, seed}"]

    subgraph router["Router"]
        B["generation.py\nPydantic schema validation"]
    end

    subgraph engine["generation_engine.py — generate_datasets()"]
        C["nextval('seq_run_id')\nINSERT INTO metadata_runs"]
        D{"Template\nspecified?"}
        E["template_library.py\n_load_templates_from_disk()\nfile-mtime cache hit/miss"]
        F["Merge template fields\nwith request overrides"]
        G["Compute per-field seed\nhomogeneity roll per field\n(uses random.Random instance)"]
        H["_generate_field_value(faker, field)\nFaker · formula Jinja2\nnull_probability · condition gate\nweighted random_element"]
        I{"group_config\nspecified?"}
        J["Parent rows → N groups\nchild rows get parent_id\nsplit_pct controls mix"]
        K["db.executemany()\nbatch INSERT 5 000 rows/call"]
    end

    subgraph persist["DuckDB"]
        L["CREATE TABLE dataset_{uuid}\ninferred column types\n(INTEGER/DOUBLE/BOOLEAN/DATE/VARCHAR)"]
        M["INSERT INTO metadata_datasets\ndataset_id · run_id · name\ntable_name · columns_json · row_count"]
    end

    N["GenerateResponse\n{dataset_id, name,\nrow_count, columns}"]

    A --> B --> C --> D
    D -->|yes| E --> F --> G
    D -->|no| G
    G --> H --> I
    I -->|yes| J --> K
    I -->|no| K
    K --> L --> M --> N
```

---

### 2b. Kaggle Import Pipeline

```mermaid
flowchart TD
    A["POST /kaggle/import\n{owner, slug, file_name,\ndataset_name?, max_rows?}"]

    subgraph auth["Credential setup"]
        B["_setup_env()\nos.environ KAGGLE_API_TOKEN\nor KAGGLE_USERNAME + KEY\nor ~/.kaggle/kaggle.json"]
        C["KaggleApi().authenticate()"]
    end

    subgraph dl["Download  (in TemporaryDirectory)"]
        D["dataset_download_file()\nsingle-file attempt"]
        E{".zip or .csv\nwritten to disk?"}
        F["zipfile.ZipFile\nextract target CSV"]
        G["Fallback:\ndataset_download_files()\nfull dataset zip + unzip=True"]
        H["rglob('*.csv')\nmatch file_name or first found"]
    end

    subgraph ingest["_ingest_csv()"]
        I["CREATE TABLE dataset_{uuid} AS\nSELECT * FROM read_csv_auto(?)\nnormalize_names=true\nignore_errors=true\nLIMIT ?  ← parameterized"]
        J["DESCRIBE table → columns\nSELECT COUNT(*) → row_count"]
        K["INSERT INTO metadata_datasets\nsource = 'kaggle:owner/slug/file'"]
    end

    L["KaggleImportResponse\n{dataset_id, name,\ntable_name, row_count, columns}"]

    A --> B --> C --> D --> E
    E -->|zip found| F --> I
    E -->|direct csv| I
    E -->|error / 404| G --> H --> I
    I --> J --> K --> L
```

---

### 2c. Export Pipeline

```mermaid
flowchart LR
    A["GET /datasets/{id}/export/csv"]

    subgraph router["exports.py  router"]
        B["filepath, download_name\n= export_service.export_csv(id)"]
        C["background_tasks.add_task\n(_cleanup, filepath)"]
        D["FileResponse\nfilepath = token.csv\nfilename = friendly.csv"]
    end

    subgraph svc["export_service.py"]
        E["get_dataset(id)\n→ name, table_name"]
        F["validate_table_name()"]
        G["_safe_export_path('csv')\n/tmp/faker_exports/\ntoken_hex(16).csv"]
        H["DuckDB\nCOPY table TO filepath\n(HEADER, DELIMITER ',')"]
        I["return filepath,\n sanitized_name_id.csv"]
    end

    subgraph cleanup["After response sent"]
        J["BackgroundTask\nos.unlink(filepath)"]
    end

    A --> B
    B --> E --> F --> G --> H --> I --> D
    D --> C --> J
```

---

### 2d. Aggregation & Dedup Pipeline

```mermaid
flowchart TD
    A["POST /datasets/{id}/aggregate\nor /dedup"]

    subgraph validate["Validation"]
        B["get_dataset(source_id)\n→ table_name"]
        C["validate_table_name()\nvalidate_column_name()\nper group-by + agg columns"]
    end

    subgraph build["SQL Builder  (transform_service.py)"]
        D{"aggregate\nor dedup?"}
        E["GROUP BY {cols}\nAGG_FN(col) AS alias\nCAST to DOUBLE if needed"]
        F{"strategy?"}
        G["keep_first / keep_last\nROW_NUMBER() OVER\n(PARTITION BY keys\nORDER BY col ASC/DESC)\nWHERE _rn = 1"]
        H["keep_none\nWHERE key_tuple IN\n(SELECT key_tuple GROUP BY ...\nHAVING COUNT(*) = 1)"]
    end

    subgraph persist["DuckDB"]
        I["CREATE TABLE dataset_{uuid}\nAS {sql}"]
        J["INSERT INTO metadata_datasets"]
        K["INSERT INTO metadata_aggregations\n(id = nextval('seq_aggregation_id'),\nsource_dataset, config_json)"]
    end

    L["TransformResponse\n{dataset_id, row_count, columns}"]

    A --> B --> C --> D
    D -->|aggregate| E --> I
    D -->|dedup| F
    F -->|keep_first / keep_last| G --> I
    F -->|keep_none| H --> I
    I --> J --> K --> L
```

---

## 3. Database Schema

```mermaid
erDiagram
    metadata_schema_version {
        VARCHAR version PK
        TIMESTAMP applied_at
    }

    metadata_runs {
        INTEGER run_id PK
        VARCHAR name
        VARCHAR template_name
        INTEGER row_count
        INTEGER homogeneity
        INTEGER seed
        TIMESTAMP created_at
    }

    metadata_datasets {
        VARCHAR dataset_id PK
        INTEGER run_id FK
        VARCHAR name
        VARCHAR table_name
        VARCHAR columns_json
        INTEGER row_count
        INTEGER homogeneity
        INTEGER seed
        VARCHAR source
        TIMESTAMP created_at
    }

    metadata_aggregations {
        INTEGER id PK
        VARCHAR source_dataset FK
        VARCHAR name
        VARCHAR config_json
        TIMESTAMP created_at
    }

    metadata_templates {
        VARCHAR name PK
        VARCHAR category
        VARCHAR description
        VARCHAR xml_content
        TIMESTAMP created_at
        TIMESTAMP updated_at
    }

    metadata_iso_cache {
        VARCHAR cache_key PK
        VARCHAR data_json
        TIMESTAMP fetched_at
    }

    dataset_snapshot {
        VARCHAR dataset_id
        VARCHAR col_1
        VARCHAR col_2
        VARCHAR col_N
    }

    metadata_runs        ||--o{ metadata_datasets     : "run_id (one run → many datasets)"
    metadata_datasets    ||--o{ metadata_aggregations  : "source_dataset (cascade-deleted)"
    metadata_datasets    ||--||  dataset_snapshot       : "table_name → dataset_{uuid}"
```

> **`dataset_snapshot`** is a placeholder for the family of dynamic tables named `dataset_{uuid4}`. Each row in `metadata_datasets` maps to exactly one such table via the `table_name` column. These tables are immutable after creation — aggregation and dedup always produce a new `dataset_{uuid}` table.

### Sequences

| Sequence | Used by | Purpose |
|---|---|---|
| `seq_run_id` | `metadata_runs.run_id` | Monotonic run counter |
| `seq_aggregation_id` | `metadata_aggregations.id` | Monotonic aggregation counter (separate to avoid collisions with runs) |

### Migration history

| Migration | What it adds |
|---|---|
| `001_initial_schema` | `seq_run_id` · `metadata_templates` · `metadata_runs` · `metadata_aggregations` · `metadata_datasets` |
| `002_iso_cache` | `metadata_iso_cache` |
| `003_indexes` | Indexes on `metadata_datasets(name)` and `metadata_datasets(created_at DESC)` |
| `004_template_runs_relation` | `metadata_runs.template_name` column |
| `005_dataset_source` | `metadata_datasets.source` column |
| `006_aggregation_sequence` | `seq_aggregation_id` sequence |
