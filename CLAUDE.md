# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A collection of standalone Python CLI tools for web scraping, PDF extraction, CSV transformation, and Excel data manipulation. On top of these, `mcp_server.py` exposes the same logic as **10 MCP tools** for Claude Desktop, and `weather_alert_agent.py` is an example agent that consumes those tools. Each CLI script has a matching Jupyter notebook (`.ipynb`) mirroring its logic.

The intended evolution of this repo is: **CLI script → importable functions → MCP tool → agent that orchestrates tools.** Keep new work compatible with that pipeline (see "Conventions for new code" below).

## Running the Scripts

All scripts are invoked directly with `python <script>.py --help` for full usage. Key examples:

```bash
# Static HTML scraper (requests + BeautifulSoup)
python web_scraper.py --url "https://example.com" --tag td --output out.csv
python web_scraper.py --url "https://example.com" --list --output out.csv

# Multi-field attribute scraper (static)
python attr_scraper.py --url "https://example.com" \
    --parent-tag div --parent-class "product" --child-tag span \
    --fields "name:data-field:title" "sku:data-field:sku" \
    --output products.csv

# Playwright version (JS-rendered pages — preferred over Selenium)
python attr_scraper_playwright.py --url "https://example.com" \
    --wait-for "span[databind='text: name']" \
    --fields "brand:databind:text: name" "reg:databind:text: regNumber" \
    --output out.csv

# Selenium version (requires Chrome + ChromeDriver on PATH)
python attr_scraper_selenium.py --url "https://example.com" \
    --wait-for "span[databind='text: name']" \
    --fields "brand:databind:text: name" "reg:databind:text: regNumber" \
    --output out.csv

# Excel merge (2+ files, optional key column)
python excel_merge.py --files a.xlsx b.xlsx c.xlsx --merge-key ID --output merged.xlsx

# PDF extractor — text mode (one row per page)
python pdf_extractor.py --input report.pdf --mode text --output pages.csv

# PDF extractor — table mode (structured rows from page 1-3)
python pdf_extractor.py --input data.pdf --mode table --pages 1-3 --output table.csv

# CSV transformer — filter, dedupe, rename, select columns
python csv_transformer.py --input data.csv \
    --filter "status == 'active'" \
    --dedupe --dedupe-cols id \
    --rename "product_name:name" \
    --select id name price \
    --output clean.csv

# Weather alert agent (stdout dry run — no email/Slack needed)
python weather_alert_agent.py --lat 30.26 --lon -97.74 --channel stdout
```

## Installing Dependencies

```bash
pip install -r requirements.txt
playwright install chromium   # additionally required for attr_scraper_playwright
```

`attr_scraper_selenium` also requires Chrome and ChromeDriver installed and on `PATH`.

## Running Tests

```bash
python -m pytest tests/ -v
```

`tests/test_smoke.py` is a single smoke-test suite (57 tests) covering every module. **It requires no network** — all HTTP fetchers (`fetch_page_*`, `requests.get`, the weather sources) are monkeypatched with canned HTML/JSON, and PDF/Excel/CSV tests use `tmp_path` fixtures. `tests/conftest.py` inserts the repo root onto `sys.path` so the suite runs from any working directory.

When you add a tool or change behavior, add a matching test. The suite is the fastest way to confirm you haven't broken the MCP layer or the agent.

## Architecture

### Scraper tool family (`attr_scraper*`)

`attr_scraper.py`, `attr_scraper_playwright.py`, and `attr_scraper_selenium.py` share identical logic for `parse_field_definitions`, `scrape_records`, and `write_csv`. The only difference is the `fetch_page_*` function:

- `attr_scraper.py` — `fetch_page` via `requests.get` (static HTML only)
- `attr_scraper_playwright.py` — `fetch_page_playwright`, Playwright `sync_playwright` + `page.wait_for_selector` (timeout in **milliseconds**)
- `attr_scraper_selenium.py` — `fetch_page_selenium`, Selenium `WebDriverWait` + `EC.presence_of_element_located` (timeout in **seconds**)

When the page is JavaScript-rendered, prefer Playwright over Selenium (no separate ChromeDriver needed).

**Field definition format:** `column_name:attr_name:attr_value` — e.g. `"brand:databind:text: name"` finds `<span databind="text: name">` within each parent element and maps its text to the `brand` column. The format is split on `:` with a limit of 3 parts, so `attr_value` may itself contain colons.

> Known duplication: the three shared scraper functions are copy-pasted across the three files. If you touch one, mirror the change in all three. A future refactor could extract them into a `scraper_utils.py` — but the MCP server currently imports `parse_field_definitions`/`scrape_records` from `attr_scraper` only, so update that import if you do.

### `web_scraper.py`

Simpler, single-column output. Extraction modes selected by CLI flags:
1. `--list` → all `<li>` text
2. `--col-index N` → Nth `<td>` from every `<tr>`
3. `--class-name` → all `<tag class="...">` text
4. Default → all `<tag>` text (tag defaults to `td`)

### `excel_merge.py`

Chains pandas outer merges across 2+ Excel files in the order given. Each merge step appends a `_merge_N` indicator column (`left_only` / `right_only` / `both`) which is retained in the output. **These indicator columns are pandas `CategoricalDtype` and are not directly JSON-serializable** — the MCP `merge_excel` tool works around this by serializing through `DataFrame.to_json()`.

### `pdf_extractor.py`

Two modes selected by `--mode`:
- `text` — extracts raw text from each page; one row per page with `page` + `text` columns
- `table` — extracts a structured table using the first row as the header; `--table-index` selects which table per page (0-based) when multiple tables exist

`--pages` accepts comma-separated values and ranges (e.g. `1,3,5-7`); omitting it processes all pages.

`load_pdf` calls `sys.exit()` on a missing file — **do not import it into the MCP server or any agent** (see conventions). The MCP `extract_pdf` tool opens the file with `pdfplumber.open()` directly instead.

### `csv_transformer.py`

Applies up to four transformations in a fixed order regardless of flag sequence: **filter → dedupe → rename → select**. `--filter` uses pandas `query()` syntax. `--rename` uses `old:new` pairs, consistent with the `name:attr:value` convention in the scraper family. All transformation functions accept and return plain DataFrames, making them directly importable.

`load_csv` calls `sys.exit()` on a missing file — same caveat as `load_pdf`. The MCP `transform_csv` tool uses `pd.read_csv()` directly.

### `mcp_server.py` — MCP server (10 tools)

Built on `FastMCP` (`from mcp.server.fastmcp import FastMCP`). Each tool is a plain function decorated with `@mcp.tool()`. The server imports the existing CLI logic and adapts it; it deliberately avoids the `load_*` helpers that call `sys.exit()`.

| Tool | Wraps / does |
|---|---|
| `scrape_web` | `web_scraper` extraction modes |
| `scrape_attributes` | `attr_scraper` static scraping |
| `scrape_attributes_playwright` | Playwright scraping; param `timeout_ms` (milliseconds) |
| `scrape_attributes_selenium` | Selenium scraping; param `timeout_seconds` (seconds) |
| `fetch_json` | GET any JSON REST endpoint; merges a default User-Agent with caller headers |
| `merge_excel` | `excel_merge` chained merge + `comparison_summary` |
| `extract_pdf` | `pdf_extractor` text/table modes; validates `mode` explicitly |
| `transform_csv` | `csv_transformer` pipeline; adds `columns` + `initial_row_count` |
| `list_directory` | Glob a directory → name/size/modified, newest first, max 500 |
| `describe_dataset` | CSV/Excel structural summary: shape, dtypes, null counts, numeric stats, sample rows |

**Tool return convention:** every tool returns a JSON **string** via `json.dumps(..., ensure_ascii=False)`. The standard shape is `{"record_count": N, "records": [...]}`. Some tools add keys (`merge_excel` → `comparison_summary`; `transform_csv` → `columns`, `initial_row_count`). Use `default=str` in `json.dumps` when a DataFrame may contain non-JSON-native dtypes.

**Errors:** tools `raise` (e.g. `ValueError`, `FileNotFoundError`) rather than printing and exiting. FastMCP surfaces the exception to the client. Never call `sys.exit()` from a tool — it kills the whole server.

Run/inspect locally:
```bash
python mcp_server.py          # starts the server, blocks on stdin
mcp dev mcp_server.py         # opens the MCP Inspector at http://localhost:5173
```

## Agents

### `weather_alert_agent.py`

Heat safety alert agent for outdoor work crews. Pipeline: fetch conditions from **three sources** (NWS, Open-Meteo, OpenWeatherMap) → `average_conditions` (skips any source that fails; raises only if all fail) → `classify_risk` (OSHA heat-index thresholds: low/moderate/high/very_high/extreme) → `generate_alert` (Claude API, model `claude-sonnet-4-6`, with a cached system prompt) → `send_alert` (Gmail SMTP_SSL / Slack webhook / stdout).

It imports `mcp_server.fetch_json` directly to reach the weather APIs, demonstrating the "agent consumes MCP tools" pattern. Tests monkeypatch `mcp_server.fetch_json` to exercise the agent offline.

Config comes from environment variables (`.env` via `python-dotenv`; copy `.env.example`). `validate_delivery_config()` runs first in `main()` so a misconfigured channel fails **before** spending a paid Claude API call. OpenWeatherMap is optional — if `OPENWEATHERMAP_API_KEY` is absent the agent averages the remaining two sources.

## Notebooks

Each `.py` CLI script has a paired `.ipynb` that mirrors its logic. When modifying a script, keep the corresponding notebook in sync. The `csv_transformer.ipynb` writes a self-contained sample CSV in Section 1 so it can be run without any external file. (`mcp_server.py`, `weather_alert_agent.py`, `generate_docx.py`, and the tests have no notebooks.)

## Setup Documents

`MCP_SETUP_GUIDE.md` is the canonical reference for onboarding a new laptop and standing up the MCP server in Claude Desktop. It covers prerequisites, implementation steps, testing, and the Claude Desktop config block.

Run `python generate_docx.py` to regenerate `MCP_SETUP_GUIDE.docx` (Word format) after editing the markdown. `generate_docx.py` is a small standalone markdown→docx converter (uses `python-docx`); it maps `#`/`##`/`###` to Word headings, fenced code to a monospace style, and `-`/`N.` to list styles.

## Conventions for new code (read before adding a tool or agent)

These come from prior review cycles — following them keeps the CLI → MCP → agent pipeline working:

1. **Never call `sys.exit()` in a function meant to be imported.** Raise an exception instead. The `load_pdf`/`load_csv` helpers violate this and must not be imported into the server or agents.
2. **Keep core logic in functions that take and return plain data** (DataFrames, dicts, lists) with no `print`/`argparse`/exit side effects. CLI `main()` and MCP tools are thin wrappers over these.
3. **MCP tools return a JSON string**, normally `{"record_count": N, "records": [...]}`, built with `json.dumps(..., ensure_ascii=False)`. Add `default=str` if non-native dtypes may appear (pandas Categorical/Timestamp).
4. **Document timeout/quantity units in the parameter name or docstring.** Playwright uses ms, Selenium uses seconds — this asymmetry has caused confusion.
5. **Never log secrets.** When an API key is embedded in a URL or payload, catch the exception and log `type(e).__name__` (or a scrubbed message), not the raw exception — see `fetch_openweathermap`.
6. **Validate required config early**, before doing expensive or paid work (network, LLM calls) — mirror `validate_delivery_config()`.
7. **Add a smoke test** in `tests/test_smoke.py` for any new tool/function, monkeypatching network calls so the suite stays offline and fast.
8. **`requirements.txt` is kept alphabetical.** Add new deps in order.
