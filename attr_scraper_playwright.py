"""
attr_scraper_playwright.py — Multi-field record scraper using Playwright for JavaScript-rendered pages.

Use this when requests returns empty results because the page loads data
via JavaScript. Playwright is generally faster and more reliable than
Selenium and doesn't require a separate ChromeDriver installation.

Requirements:
    pip install playwright beautifulsoup4
    playwright install chromium

Usage:
    python attr_scraper_playwright.py --url <URL> --wait-for <CSS_SELECTOR> [options]

Options:
    --url               Target URL to scrape (required)
    --wait-for          CSS selector to wait for before scraping, confirms JS has loaded (required)
    --timeout           Max milliseconds to wait for content (default: 15000)
    --parent-tag        HTML tag wrapping each record (default: span)
    --parent-class      CSS class to filter parent elements (optional)
    --child-tag         Tag to search within each parent (default: span)
    --fields            Field definitions as column_name:attr_name:attr_value
    --output            Output CSV path (default: output.csv)
    --headed            Show browser window instead of running headless (useful for debugging)

Example:
    python attr_scraper_playwright.py \\
        --url "https://www.cdms.net/Label-Database/Advanced-Search#Result-products" \\
        --wait-for "span[databind='text: name']" \\
        --fields "brand_name:databind:text: name" "reg_number:databind:text: regNumber" \\
        --output active_ingredients.csv
"""

import argparse
import csv
import sys

from bs4 import BeautifulSoup
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def fetch_page_playwright(url: str, wait_for: str, timeout: int, headless: bool) -> str:
    """
    Launch a Chromium browser, navigate to the URL, wait until the target
    CSS selector appears (confirming JS has rendered), then return the
    full page HTML as a string.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(user_agent="Mozilla/5.0")
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_selector(wait_for, timeout=timeout)
            html = page.content()
        except PlaywrightTimeoutError:
            print(f"Timeout: '{wait_for}' did not appear within {timeout}ms.")
            print("The page may require login, a different selector, or more wait time.")
            html = page.content()  # Return whatever loaded so far
        finally:
            browser.close()
    return html


def parse_field_definitions(field_args: list[str]) -> list[tuple[str, str, str]]:
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
    kwargs = {"class_": parent_class} if parent_class else {}
    parents = soup.find_all(parent_tag, **kwargs)

    records = []
    for parent in parents:
        record = {}
        for col_name, attr_name, attr_value in fields:
            child = parent.find(child_tag, attrs={attr_name: attr_value})
            record[col_name] = child.get_text(strip=True) if child else ""
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
    parser = argparse.ArgumentParser(description="Playwright-based multi-field record scraper")
    parser.add_argument("--url", required=True)
    parser.add_argument("--wait-for", dest="wait_for", required=True,
                        help="CSS selector to wait for before scraping")
    parser.add_argument("--timeout", type=int, default=15000,
                        help="Timeout in milliseconds (default: 15000)")
    parser.add_argument("--parent-tag", default="span")
    parser.add_argument("--parent-class", dest="parent_class")
    parser.add_argument("--child-tag", default="span", dest="child_tag")
    parser.add_argument("--fields", nargs="+", required=True)
    parser.add_argument("--output", default="output.csv")
    parser.add_argument("--headed", dest="headless", action="store_false", default=True,
                        help="Show browser window (useful for debugging)")
    args = parser.parse_args()

    fields = parse_field_definitions(args.fields)
    if not fields:
        print("No valid field definitions. Exiting.")
        sys.exit(1)

    print(f"Launching browser... fetching: {args.url}")
    html = fetch_page_playwright(args.url, args.wait_for, args.timeout, args.headless)

    soup = BeautifulSoup(html, "html.parser")
    records = scrape_records(soup, args.parent_tag, args.parent_class, args.child_tag, fields)

    if not records:
        print("No records found. Try --headed to watch the browser and diagnose.")
        sys.exit(0)

    print(f"Found {len(records)} records.")
    write_csv(records, [f[0] for f in fields], args.output)


if __name__ == "__main__":
    main()
