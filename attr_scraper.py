"""
attr_scraper.py — General-purpose multi-field record scraper using requests + BeautifulSoup.

Designed for pages where data is structured as repeated parent elements,
each containing child elements identified by a specific HTML attribute
(e.g. data-bind, data-field, id, name). Extracts multiple fields per record
and writes a multi-column CSV.

Usage:
    python attr_scraper.py --url <URL> [options]

Options:
    --url               Target URL to scrape (required)
    --parent-tag        HTML tag that wraps each record (default: span)
    --parent-class      CSS class to filter parent elements (optional)
    --fields            One or more field definitions in the format:
                          column_name:attr_name:attr_value
                        Example:
                          --fields "brand:databind:text: name" "reg:databind:text: regNumber"
    --child-tag         Tag to search within each parent (default: span)
    --output            Output CSV file path (default: output.csv)

Examples:
    # cdms.net-style — extract brand name and registration number from databind spans
    python attr_scraper.py \\
        --url "https://www.cdms.net/Label-Database/Advanced-Search#Result-products" \\
        --parent-tag span \\
        --child-tag span \\
        --fields "brand_name:databind:text: name" "reg_number:databind:text: regNumber" \\
        --output active_ingredients.csv

    # Generic product page — extract title and SKU from data-field attributes
    python attr_scraper.py \\
        --url "https://example.com/products" \\
        --parent-tag div --parent-class "product-tile" \\
        --child-tag span \\
        --fields "title:data-field:product-name" "sku:data-field:product-sku" \\
        --output products.csv
"""

import argparse
import csv
import sys

import requests
from bs4 import BeautifulSoup


def fetch_page(url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.content


def parse_field_definitions(field_args: list[str]) -> list[tuple[str, str, str]]:
    """
    Parse field definitions from CLI args.
    Each arg is formatted as "column_name:attr_name:attr_value".
    Returns a list of (column_name, attr_name, attr_value) tuples.
    """
    fields = []
    for f in field_args:
        parts = f.split(":", 2)
        if len(parts) != 3:
            print(f"Warning: skipping malformed field definition '{f}' (expected name:attr:value)")
            continue
        fields.append((parts[0], parts[1], parts[2]))
    return fields


def scrape_records(
    soup: BeautifulSoup,
    parent_tag: str,
    parent_class: str | None,
    child_tag: str,
    fields: list[tuple[str, str, str]],
) -> list[dict]:
    """
    Find all parent elements, then for each one extract child elements
    by matching a specific attribute value. Returns a list of dicts,
    one per parent element.
    """
    kwargs = {"class_": parent_class} if parent_class else {}
    parents = soup.find_all(parent_tag, **kwargs)

    records = []
    for parent in parents:
        record = {}
        for col_name, attr_name, attr_value in fields:
            child = parent.find(child_tag, attrs={attr_name: attr_value})
            record[col_name] = child.get_text(strip=True) if child else ""
        # Only include the record if at least one field has a value
        if any(record.values()):
            records.append(record)

    return records


def write_csv(records: list[dict], fieldnames: list[str], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {len(records)} records to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(description="Multi-field attribute-based record scraper")
    parser.add_argument("--url", required=True, help="URL to scrape")
    parser.add_argument("--parent-tag", default="span", help="Tag wrapping each record (default: span)")
    parser.add_argument("--parent-class", dest="parent_class", help="CSS class to filter parent elements")
    parser.add_argument("--child-tag", default="span", dest="child_tag", help="Tag to search within each parent (default: span)")
    parser.add_argument(
        "--fields",
        nargs="+",
        required=True,
        help="Field definitions as column_name:attr_name:attr_value",
    )
    parser.add_argument("--output", default="output.csv", help="Output CSV path (default: output.csv)")
    args = parser.parse_args()

    fields = parse_field_definitions(args.fields)
    if not fields:
        print("No valid field definitions provided. Exiting.")
        sys.exit(1)

    print(f"Fetching: {args.url}")
    try:
        content = fetch_page(args.url)
    except requests.RequestException as e:
        print(f"Error fetching page: {e}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(content, "html.parser")

    records = scrape_records(soup, args.parent_tag, args.parent_class, args.child_tag, fields)

    if not records:
        print("No records found. Try adjusting --parent-tag, --parent-class, or --fields.")
        sys.exit(0)

    print(f"Found {len(records)} records.")
    fieldnames = [f[0] for f in fields]
    write_csv(records, fieldnames, args.output)


if __name__ == "__main__":
    main()
