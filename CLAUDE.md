# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A collection of standalone Python CLI tools for web scraping and Excel data manipulation. Each tool has a matching Jupyter notebook (`.ipynb`) for interactive exploration of the same logic.

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
```

## Installing Dependencies

There is no `requirements.txt`. Install per-tool as needed:

```bash
pip install requests beautifulsoup4          # web_scraper, attr_scraper
pip install playwright beautifulsoup4        # attr_scraper_playwright
playwright install chromium
pip install selenium beautifulsoup4          # attr_scraper_selenium (+ Chrome + ChromeDriver)
pip install pandas openpyxl                  # excel_merge
```

## Architecture

### Scraper tool family (`attr_scraper*`)

`attr_scraper.py`, `attr_scraper_playwright.py`, and `attr_scraper_selenium.py` share identical logic for `parse_field_definitions`, `scrape_records`, and `write_csv`. The only difference is the `fetch_page_*` function:

- `attr_scraper.py` — `requests.get` (static HTML only)
- `attr_scraper_playwright.py` — Playwright `sync_playwright` + `page.wait_for_selector`
- `attr_scraper_selenium.py` — Selenium `WebDriverWait` + `EC.presence_of_element_located`

When the page is JavaScript-rendered, prefer Playwright over Selenium (no separate ChromeDriver needed).

**Field definition format:** `column_name:attr_name:attr_value` — e.g. `"brand:databind:text: name"` finds `<span databind="text: name">` within each parent element and maps its text to the `brand` column. The format is split on `:` with a limit of 3 parts, so `attr_value` may itself contain colons.

### `web_scraper.py`

Simpler, single-column output. Three extraction modes selected by CLI flags:
1. `--list` → all `<li>` text
2. `--col-index N` → Nth `<td>` from every `<tr>`
3. `--class-name` → all `<tag class="...">` text
4. Default → all `<tag>` text (tag defaults to `td`)

### `excel_merge.py`

Chains pandas outer merges across 2+ Excel files in the order given. Each merge step appends a `_merge_N` indicator column (`left_only` / `right_only` / `both`) which is retained in the output, making it easy to see which rows came from which source files.

## Notebooks

Each `.py` script has a paired `.ipynb` that mirrors its logic. When modifying a script, keep the corresponding notebook in sync.
