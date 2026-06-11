"""MCP server — exposes the i-Mars96 CLI toolkit as Claude Desktop tools."""

import json
import pathlib
from datetime import datetime, timezone

import pdfplumber
import pandas as pd
import requests
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

from web_scraper import (
    fetch_page as fetch_page_web,
    scrape_by_class,
    scrape_table_column,
    scrape_list_items,
)
from attr_scraper import (
    fetch_page as fetch_page_static,
    parse_field_definitions,
    scrape_records,
)
from attr_scraper_playwright import fetch_page_playwright
from attr_scraper_selenium import fetch_page_selenium
from excel_merge import load_files, reset_indexes, merge_dataframes, compare_dataframes
from pdf_extractor import parse_page_numbers, extract_text, extract_tables
from csv_transformer import (
    parse_rename_definitions,
    apply_filter,
    apply_deduplication,
    apply_rename,
    apply_column_selection,
)

mcp = FastMCP("i-mars96-toolkit")


@mcp.tool()
def scrape_web(
    url: str,
    tag: str = "td",
    class_name: str | None = None,
    col_index: int | None = None,
    scrape_list: bool = False,
) -> str:
    """
    Scrape a static HTML page with requests + BeautifulSoup.

    Extraction modes (checked in order):
    - scrape_list=True  → all <li> text
    - col_index set     → Nth <td> from every <tr>
    - class_name set    → all <tag class="..."> text
    - default           → all <tag> text (tag defaults to "td")

    Returns JSON with record_count and records [{value: ...}].
    """
    content = fetch_page_web(url)
    soup = BeautifulSoup(content, "html.parser")

    if scrape_list:
        data = scrape_list_items(soup)
    elif col_index is not None:
        data = scrape_table_column(soup, col_index)
    elif class_name:
        data = scrape_by_class(soup, tag, class_name)
    else:
        data = [el.get_text(strip=True) for el in soup.find_all(tag) if el.get_text(strip=True)]

    records = [{"value": v} for v in data]
    return json.dumps({"record_count": len(records), "records": records}, ensure_ascii=False)


@mcp.tool()
def fetch_json(
    url: str,
    headers: dict | None = None,
) -> str:
    """
    Fetch a JSON REST API endpoint and return its contents.

    Merges any provided headers with a default User-Agent. Raises on non-2xx responses.
    Returns JSON with the parsed API response nested under the key "data".

    Useful for APIs like NWS (api.weather.gov), Open-Meteo, OpenWeatherMap, etc.
    """
    merged_headers = {"User-Agent": "Mozilla/5.0", **(headers or {})}
    response = requests.get(url, headers=merged_headers, timeout=10)
    response.raise_for_status()
    return json.dumps({"data": response.json()}, ensure_ascii=False)


@mcp.tool()
def scrape_attributes(
    url: str,
    fields: list[str],
    parent_tag: str = "span",
    parent_class: str | None = None,
    child_tag: str = "span",
) -> str:
    """
    Scrape a static HTML page for structured multi-field records.

    Each field definition: "column_name:attr_name:attr_value"
    e.g. "brand:databind:text: name" maps the text of
    <span databind="text: name"> inside each parent to the "brand" column.

    Returns JSON with record_count and records (one dict per parent element).
    """
    content = fetch_page_static(url)
    soup = BeautifulSoup(content, "html.parser")
    field_defs = parse_field_definitions(fields)
    records = scrape_records(soup, parent_tag, parent_class, child_tag, field_defs)
    return json.dumps({"record_count": len(records), "records": records}, ensure_ascii=False)


@mcp.tool()
def scrape_attributes_playwright(
    url: str,
    wait_for: str,
    fields: list[str],
    parent_tag: str = "span",
    parent_class: str | None = None,
    child_tag: str = "span",
    timeout_ms: int = 15000,
    headless: bool = True,
) -> str:
    """
    Scrape a JavaScript-rendered page using Playwright (Chromium). No ChromeDriver needed.

    Waits for the wait_for CSS selector to appear before scraping, confirming JS has loaded.
    timeout_ms is in milliseconds (default 15000). Set headless=False to watch the browser.

    Returns JSON with record_count and records.
    """
    html = fetch_page_playwright(url, wait_for, timeout_ms, headless)
    soup = BeautifulSoup(html, "html.parser")
    field_defs = parse_field_definitions(fields)
    records = scrape_records(soup, parent_tag, parent_class, child_tag, field_defs)
    return json.dumps({"record_count": len(records), "records": records}, ensure_ascii=False)


@mcp.tool()
def scrape_attributes_selenium(
    url: str,
    wait_for: str,
    fields: list[str],
    parent_tag: str = "span",
    parent_class: str | None = None,
    child_tag: str = "span",
    timeout_seconds: int = 15,
    headless: bool = True,
) -> str:
    """
    Scrape a JavaScript-rendered page using Selenium + Chrome. Requires Chrome + ChromeDriver on PATH.

    Waits for the wait_for CSS selector to appear before scraping, confirming JS has loaded.
    timeout_seconds is in seconds (default 15). Set headless=False to watch the browser.

    Returns JSON with record_count and records.
    """
    html = fetch_page_selenium(url, wait_for, timeout_seconds, headless)
    soup = BeautifulSoup(html, "html.parser")
    field_defs = parse_field_definitions(fields)
    records = scrape_records(soup, parent_tag, parent_class, child_tag, field_defs)
    return json.dumps({"record_count": len(records), "records": records}, ensure_ascii=False)


@mcp.tool()
def merge_excel(
    file_paths: list[str],
    merge_key: str | None = None,
    sheet: int | str = 0,
) -> str:
    """
    Outer-merge 2+ Excel files in order using pandas.

    file_paths: list of absolute paths to .xlsx files (minimum 2).
    merge_key: column name to join on; omit to merge on all shared columns.
    sheet: sheet name or 0-based index to read from each file (default: 0).

    Returns JSON with record_count, records, and comparison_summary showing
    left_only / right_only / both counts for each merge step.
    """
    named_dfs = load_files(file_paths, sheet)
    named_dfs = reset_indexes(named_dfs)
    merged = merge_dataframes(named_dfs, merge_key)
    summary = compare_dataframes(merged)
    # to_json handles pandas Categorical dtype in _merge_N indicator columns
    records = json.loads(merged.to_json(orient="records", force_ascii=False))
    return json.dumps(
        {"record_count": len(records), "records": records, "comparison_summary": summary},
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def extract_pdf(
    pdf_path: str,
    mode: str = "text",
    pages: str | None = None,
    table_index: int = 0,
) -> str:
    """
    Extract text or tables from a PDF file using pdfplumber.

    mode: "text"  → one row per page: {page: N, text: "..."}
          "table" → structured rows using the first PDF row as the header
    pages: comma-separated numbers/ranges, e.g. "1,3,5-7" (default: all pages)
    table_index: which table per page to extract, 0-based (default: 0)

    Returns JSON with record_count and records.
    """
    if mode not in ("text", "table"):
        raise ValueError(f"mode must be 'text' or 'table', got {mode!r}")
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        page_indices = parse_page_numbers(pages, total)
        if mode == "text":
            records = extract_text(pdf, page_indices)
        else:
            records = extract_tables(pdf, page_indices, table_index)
    return json.dumps({"record_count": len(records), "records": records}, ensure_ascii=False)


@mcp.tool()
def transform_csv(
    csv_path: str,
    filter_expr: str | None = None,
    dedupe: bool = False,
    dedupe_cols: list[str] | None = None,
    rename: list[str] | None = None,
    select: list[str] | None = None,
) -> str:
    """
    Filter, deduplicate, rename columns, and select columns from a CSV file.

    Operations run in fixed order regardless of argument order: filter → dedupe → rename → select.
    filter_expr: pandas query() expression, e.g. "price > 100 and status == 'active'"
    dedupe: drop exact duplicate rows; dedupe_cols limits deduplication to a column subset
    rename: list of "old:new" pairs, e.g. ["product_name:name", "Qty:quantity"]
    select: list of column names to keep, in order

    Returns JSON with record_count, initial_row_count, columns, and records.
    """
    df = pd.read_csv(csv_path)
    initial_row_count = len(df)

    if filter_expr:
        df = apply_filter(df, filter_expr)
    if dedupe:
        df = apply_deduplication(df, dedupe_cols)
    if rename:
        mapping = parse_rename_definitions(rename)
        df = apply_rename(df, mapping)
    if select:
        df = apply_column_selection(df, select)

    records = json.loads(df.to_json(orient="records", force_ascii=False))
    return json.dumps(
        {
            "record_count": len(records),
            "initial_row_count": initial_row_count,
            "columns": list(df.columns),
            "records": records,
        },
        ensure_ascii=False,
        default=str,
    )


@mcp.tool()
def list_directory(path: str, pattern: str = "*") -> str:
    """
    List files in a directory, optionally filtered by a glob pattern.

    Returns each entry's name, size_bytes, and modified timestamp (ISO 8601),
    sorted by most-recently-modified first (up to 500 entries).
    Useful for discovering available data files before calling other tools.

    Examples:
      list_directory("/data")
      list_directory("/data", pattern="*.csv")
      list_directory("/data", pattern="**/*.xlsx")
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Directory not found: {path!r}")
    if not p.is_dir():
        raise NotADirectoryError(f"Not a directory: {path!r}")

    entries = sorted(p.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)[:500]
    files = [
        {
            "name": str(e.relative_to(p)),
            "size_bytes": e.stat().st_size,
            "modified": datetime.fromtimestamp(e.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
        for e in entries
        if e.is_file()
    ]
    return json.dumps({"path": str(p.resolve()), "file_count": len(files), "files": files},
                      ensure_ascii=False)


@mcp.tool()
def describe_dataset(file_path: str, sample_rows: int = 3) -> str:
    """
    Return a structural summary of a CSV or Excel (.xlsx) file.

    Includes column names, dtypes, null counts, numeric min/max/mean, and
    a configurable number of sample rows. Lets an agent understand a dataset
    before deciding how to transform or query it.

    Returns JSON with shape, columns, dtypes, null_counts, numeric_summary,
    and sample.
    """
    p = pathlib.Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path!r}")

    suffix = p.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(file_path)
    elif suffix in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"Unsupported file type {suffix!r}. Use .csv or .xlsx.")

    numeric_summary = json.loads(
        df.describe(include="number").to_json(force_ascii=False)
    ) if not df.select_dtypes("number").empty else {}

    result = {
        "shape": {"rows": df.shape[0], "columns": df.shape[1]},
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "null_counts": df.isnull().sum().to_dict(),
        "numeric_summary": numeric_summary,
        "sample": json.loads(df.head(sample_rows).to_json(orient="records", force_ascii=False)),
    }
    return json.dumps(result, ensure_ascii=False, default=str)


if __name__ == "__main__":
    mcp.run()
