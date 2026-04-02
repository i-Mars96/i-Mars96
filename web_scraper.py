"""
web_scraper.py — General-purpose HTML table/list scraper using requests + BeautifulSoup.

Usage:
    python web_scraper.py --url <URL> [options]

Options:
    --url           Target URL to scrape (required)
    --tag           HTML tag to search for (default: td)
    --class-name    CSS class to filter by (optional)
    --col-index     Column index to extract from table rows (optional, for <tr>/<td> tables)
    --output        Output CSV file path (default: output.csv)
    --list          Scrape <li> elements instead of table cells
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


def scrape_by_class(soup: BeautifulSoup, tag: str, class_name: str) -> list[str]:
    """Extract text from all tags matching a CSS class."""
    elements = soup.find_all(tag, class_=class_name)
    return [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]


def scrape_table_column(soup: BeautifulSoup, col_index: int) -> list[str]:
    """Extract a specific column from all table rows."""
    results = []
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) > col_index:
            text = cells[col_index].get_text(strip=True)
            if text:
                results.append(text)
    return results


def scrape_list_items(soup: BeautifulSoup) -> list[str]:
    """Extract text from all <li> elements."""
    return [li.get_text(strip=True) for li in soup.find_all("li") if li.get_text(strip=True)]


def write_csv(data: list[str], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["value"])
        for item in data:
            writer.writerow([item])
    print(f"Wrote {len(data)} rows to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="General-purpose HTML scraper")
    parser.add_argument("--url", required=True, help="URL to scrape")
    parser.add_argument("--tag", default="td", help="HTML tag to search (default: td)")
    parser.add_argument("--class-name", dest="class_name", help="CSS class to filter by")
    parser.add_argument("--col-index", dest="col_index", type=int, help="Column index for table scraping")
    parser.add_argument("--output", default="output.csv", help="Output CSV path (default: output.csv)")
    parser.add_argument("--list", dest="scrape_list", action="store_true", help="Scrape <li> elements")
    args = parser.parse_args()

    print(f"Fetching: {args.url}")
    try:
        content = fetch_page(args.url)
    except requests.RequestException as e:
        print(f"Error fetching page: {e}", file=sys.stderr)
        sys.exit(1)

    soup = BeautifulSoup(content, "html.parser")

    if args.scrape_list:
        data = scrape_list_items(soup)
    elif args.col_index is not None:
        data = scrape_table_column(soup, args.col_index)
    elif args.class_name:
        data = scrape_by_class(soup, args.tag, args.class_name)
    else:
        # Default: extract all text from the specified tag
        data = [el.get_text(strip=True) for el in soup.find_all(args.tag) if el.get_text(strip=True)]

    if not data:
        print("No data found. Try adjusting --tag, --class-name, or --col-index.")
        sys.exit(0)

    print(f"Found {len(data)} items.")
    write_csv(data, args.output)


if __name__ == "__main__":
    main()
