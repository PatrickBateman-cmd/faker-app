# Faker App — Command Cheatsheet

All CLI commands run from `backend/` (`cd backend`).

## Setup & Info

```sh
uv run faker init                                # Init DuckDB (creates metadata tables)
uv run faker init --db ./custom_path             # Init with custom path
uv run faker info                                # Show DB stats (datasets, templates, runs)
uv run faker info --db ./duckdb                  # With custom path
```

## Generate Data

```sh
# From template
uv run faker generate --name "mydata" --rows 5000 --template Person

# From template as JSON output
uv run faker generate --name "mydata" --rows 5000 --template Person --format json

# Inline JSON field definitions
uv run faker generate --name "test" --rows 100 --fields-json '
[{"name":"email","generator":"email","type":"string"},
 {"name":"age","generator":"random_int","type":"integer","constraint":{"min":18,"max":99}}]'

# From JSON file
uv run faker generate --name "test" --rows 1000 --fields-file ./fields.json

# Multi-dataset from JSON file
uv run faker generate --datasets-file ./two_datasets.json

# With seed (deterministic)
uv run faker generate --name "fixed" --rows 100 --template Person --seed 42

# With homogeneity
uv run faker generate --name "mixed" --rows 100 --template Person --homogeneity 70

# Quiet mode (no spinner)
uv run faker generate --name "quiet" --rows 100 --template Person --quiet

# Custom DuckDB
uv run faker generate --name "custom" --rows 50 --template Person --db ./my_data.duckdb
```

## Datasets

```sh
# List all datasets
uv run faker datasets list

# View as JSON
uv run faker datasets list --format json | jq '.[].name'

# View rows (paginated)
uv run faker datasets view <DATASET_ID>
uv run faker datasets view <DATASET_ID> --page 2 --per-page 20

# Export to CSV (default)
uv run faker datasets export <DATASET_ID> csv
uv run faker datasets export <DATASET_ID> csv --output ./my_data.csv

# Export to Parquet
uv run faker datasets export <DATASET_ID> parquet

# Export to XLSX
uv run faker datasets export <DATASET_ID> xlsx

# Delete
uv run faker datasets delete <DATASET_ID>
```

## Templates

```sh
# List all templates
uv run faker templates list

# Show template details + fields
uv run faker templates show Person

# Show as JSON
uv run faker templates show Person --format json

# Create from XML file
uv run faker templates create ./my_template.xml

# Delete
uv run faker templates delete "My Template"
```

## ISO 20022

```sh
# List business domains
uv run faker iso domains

# List messages (optionally by domain)
uv run faker iso messages
uv run faker iso messages 1          # Payments
uv run faker iso messages 6          # Securities

# Search messages
uv run faker iso search pacs
uv run faker iso search credit

# Show XSD-parsed fields
uv run faker iso xsd pacs.008.001.12

# Save as template (then generate from it)
uv run faker iso save-template pacs.008.001.12
uv run faker generate --name "iso_data" --rows 500 --template "pacs.008.001.12 - FIToFICustomerCreditTransfer"
```

## Financial (yfinance)

```sh
# Get real-time quote
uv run faker financial quote AAPL

# As JSON
uv run faker financial quote AAPL --format json

# Historical data
uv run faker financial history AAPL
uv run faker financial history AAPL --period 3mo --interval 1d
uv run faker financial history AAPL --period 1y --interval 1wk

# Batch fetch → dataset
uv run faker financial batch "AAPL,MSFT,GOOG"
uv run faker financial batch "AAPL,MSFT,GOOG" --name "tech_quotes"
# Then view:
uv run faker datasets view <DATASET_ID>
```

## Transform

```sh
# Aggregate: group-by + aggregate functions
uv run faker transform aggregate <DATASET_ID> \
  --name "by_country" --group-by "country" \
  --agg "amount:sum:total" \
  --agg "amount:avg:avg_amount"

# Deduplicate: remove duplicates by key columns
uv run faker transform dedup <DATASET_ID> \
  --name "unique" --keys "email"

# Dedup with order and strategy
uv run faker transform dedup <DATASET_ID> \
  --name "latest" --keys "email" \
  --strategy keep_last --order-by "created_at:desc"
```

## Global Options

| Flag | Shorthand | Description |
|---|---|---|
| `--db <path>` | `-d` | DuckDB path override (default: `./duckdb`) |
| `--format json` | `-f json` | JSON output instead of table |
| `--quiet` | `-q` | Suppress progress bar (generate only) |
| `--help` | | Show command help |

---

## Web API (curl) — server must be running

```sh
# Health
curl http://localhost:8000/health

# Generate
curl -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"datasets":[{"name":"demo","rows":50,"fields":[{"name":"name","generator":"name","type":"string"}]}]}'

# List datasets
curl http://localhost:8000/datasets

# View rows
curl http://localhost:8000/datasets/<ID>/rows?page=1&per_page=10

# Export
curl http://localhost:8000/datasets/<ID>/export/csv -o data.csv

# Delete
curl -X DELETE http://localhost:8000/datasets/<ID>

# ISO search
curl "http://localhost:8000/iso20022/search?q=pacs"

# ISO XSD
curl http://localhost:8000/iso20022/messages/pacs.008.001.12/xsd

# Save ISO as template
curl -X POST http://localhost:8000/iso20022/messages/pacs.008.001.12/save-template

# Financial quote
curl "http://localhost:8000/financial/quote?ticker=AAPL"

# Financial batch
curl -X POST http://localhost:8000/financial/batch-to-dataset \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["AAPL","MSFT","GOOG"],"name":"quotes"}'

# Aggregate
curl -X POST http://localhost:8000/datasets/<ID>/aggregate \
  -H 'Content-Type: application/json' \
  -d '{"name":"by_country","group_by":["country"],"aggregations":[{"column":"amount","function":"sum","alias":"total"}]}'

# Dedup
curl -X POST http://localhost:8000/datasets/<ID>/dedup \
  -H 'Content-Type: application/json' \
  -d '{"name":"unique","keys":["email"],"strategy":"keep_first"}'
```
