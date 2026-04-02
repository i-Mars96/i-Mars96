"""
attr_scraper_selenium.py — Multi-field record scraper using Selenium for JavaScript-rendered pages.

Use this when requests returns empty results because the page loads its data
via JavaScript after the initial HTML response (e.g. cdms.net, SPAs, etc.).
Selenium launches a real browser, waits for content to appear, then passes
the rendered HTML to BeautifulSoup for extraction.

Requirements:
    pip install selenium beautifulsoup4
    Chrome + ChromeDriver must be installed and on PATH
    (or use: pip install webdriver-manager)

Usage:
    python attr_scraper_selenium.py --url <URL> --wait-for <CSS_SELECTOR> [options]

Options:
    --url               Target URL to scrape (required)
    --wait-for          CSS selector to wait for before scraping, confirms JS has loaded (required)
    --timeout           Max seconds to wait for content to appear (default: 15)
    --parent-tag        HTML tag wrapping each record (default: span)
    --parent-class      CSS class to filter parent elements (optional)
    --child-tag         Tag to search within each parent (default: span)
    --fields            Field definitions as column_name:attr_name:attr_value
    --output            Output CSV path (default: output.csv)
    --headless          Run browser in headless mode, no window (default: True)

Example:
    python attr_scraper_selenium.py \\
        --url "https://www.cdms.net/Label-Database/Advanced-Search#Result-products" \\
        --wait-for "span[databind='text: name']" \\
        --fields "brand_name:databind:text: name" "reg_number:databind:text: regNumber" \\
        --output active_ingredients.csv
"""

import argparse
import csv
import sys
import time

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def build_driver(headless: bool) -> webdriver.Chrome:
    options = Options()
    if headless:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("user-agent=Mozilla/5.0")
    return webdriver.Chrome(options=options)


def fetch_page_selenium(url: str, wait_for: str, timeout: int, headless: bool) -> str:
    """
    Launch a Chrome browser, navigate to the URL, wait until the target
    CSS selector appears (confirming JS has rendered), then return the
    full page HTML as a string.
    """
    driver = build_driver(headless)
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_for))
        )
        html = driver.page_source
        return html
    except TimeoutException:
        print(f"Timeout: '{wait_for}' did not appear within {timeout}s.")
        print("The page may require login, a different selector, or more wait time.")
        return driver.page_source  # Return whatever loaded so far
    finally:
        driver.quit()


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
    parser = argparse.ArgumentParser(description="Selenium-based multi-field record scraper")
    parser.add_argument("--url", required=True)
    parser.add_argument("--wait-for", dest="wait_for", required=True,
                        help="CSS selector to wait for before scraping")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--parent-tag", default="span")
    parser.add_argument("--parent-class", dest="parent_class")
    parser.add_argument("--child-tag", default="span", dest="child_tag")
    parser.add_argument("--fields", nargs="+", required=True)
    parser.add_argument("--output", default="output.csv")
    parser.add_argument("--no-headless", dest="headless", action="store_false", default=True,
                        help="Show browser window (useful for debugging)")
    args = parser.parse_args()

    fields = parse_field_definitions(args.fields)
    if not fields:
        print("No valid field definitions. Exiting.")
        sys.exit(1)

    print(f"Launching browser... fetching: {args.url}")
    html = fetch_page_selenium(args.url, args.wait_for, args.timeout, args.headless)

    soup = BeautifulSoup(html, "html.parser")
    records = scrape_records(soup, args.parent_tag, args.parent_class, args.child_tag, fields)

    if not records:
        print("No records found. Try --no-headless to watch the browser and diagnose.")
        sys.exit(0)

    print(f"Found {len(records)} records.")
    write_csv(records, [f[0] for f in fields], args.output)


if __name__ == "__main__":
    main()
