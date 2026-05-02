"""
pdf_extractor.py — Extract text or table data from PDF files and write to CSV.

Usage:
    python pdf_extractor.py --input <FILE> [options]

Options:
    --input         Path to the source PDF file (required)
    --mode          Extraction mode: 'text' (raw text per page) or 'table' (structured rows)
                    (default: text)
    --pages         Comma-separated page numbers or ranges to process, e.g. 1,3,5-7
                    (default: all pages)
    --table-index   Which table on each page to extract, 0-indexed (default: 0)
                    Only used in 'table' mode.
    --output        Output CSV file path (default: output.csv)

Examples:
    # Extract all text, one row per page
    python pdf_extractor.py --input report.pdf --mode text --output pages.csv

    # Extract the first table from pages 1-3 of a PDF
    python pdf_extractor.py --input data.pdf --mode table --pages 1-3 --output table.csv

    # Extract the second table from every page
    python pdf_extractor.py --input data.pdf --mode table --table-index 1 --output table2.csv
"""

import argparse
import csv
import sys

import pdfplumber


def load_pdf(path: str) -> pdfplumber.PDF:
    if not __import__("pathlib").Path(path).exists():
        print(f"Error: file not found: '{path}'", file=sys.stderr)
        sys.exit(1)
    return pdfplumber.open(path)


def parse_page_numbers(pages_arg: str | None, total_pages: int) -> list[int]:
    """
    Parse a pages string like "1,3,5-7" into a sorted list of 0-based page indices.
    Returns all pages when pages_arg is None.
    """
    if pages_arg is None:
        return list(range(total_pages))

    indices = set()
    for part in pages_arg.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            indices.update(range(int(start) - 1, int(end)))
        else:
            indices.add(int(part) - 1)

    return sorted(i for i in indices if 0 <= i < total_pages)


def extract_text(pdf: pdfplumber.PDF, page_indices: list[int]) -> list[dict]:
    """Extract raw text from each page. Returns one dict per page with 'page' and 'text' keys."""
    records = []
    for i in page_indices:
        text = pdf.pages[i].extract_text()
        if text and text.strip():
            records.append({"page": i + 1, "text": text.strip()})
    return records


def extract_tables(
    pdf: pdfplumber.PDF,
    page_indices: list[int],
    table_index: int,
) -> list[dict]:
    """
    Extract a specific table from each page. Uses the first non-null row as the header.
    Returns a flat list of row dicts, each including a 'page' column.
    """
    records = []
    for i in page_indices:
        tables = pdf.pages[i].extract_tables()
        if not tables or table_index >= len(tables):
            continue
        rows = [r for r in tables[table_index] if any(c for c in r)]
        if len(rows) < 2:
            continue
        header = [str(c) if c is not None else "" for c in rows[0]]
        for row in rows[1:]:
            record = {"page": i + 1}
            for col, val in zip(header, row):
                record[col] = val if val is not None else ""
            records.append(record)
    return records


def write_csv(records: list[dict], fieldnames: list[str], output_path: str) -> None:
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"Wrote {len(records)} records to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(description="PDF text and table extractor")
    parser.add_argument("--input", required=True, help="Path to the PDF file")
    parser.add_argument("--mode", choices=["text", "table"], default="text",
                        help="Extraction mode: text or table (default: text)")
    parser.add_argument("--pages", default=None,
                        help="Pages to process, e.g. 1,3,5-7 (default: all)")
    parser.add_argument("--table-index", dest="table_index", type=int, default=0,
                        help="Which table per page to extract, 0-indexed (default: 0)")
    parser.add_argument("--output", default="output.csv",
                        help="Output CSV path (default: output.csv)")
    args = parser.parse_args()

    with load_pdf(args.input) as pdf:
        total = len(pdf.pages)
        print(f"Opened '{args.input}': {total} page(s)")

        page_indices = parse_page_numbers(args.pages, total)
        print(f"Processing {len(page_indices)} page(s) in '{args.mode}' mode.")

        if args.mode == "text":
            records = extract_text(pdf, page_indices)
            fieldnames = ["page", "text"]
        else:
            records = extract_tables(pdf, page_indices, args.table_index)
            fieldnames = list(records[0].keys()) if records else ["page"]

    if not records:
        print("No data extracted. Try adjusting --pages, --mode, or --table-index.")
        sys.exit(0)

    print(f"Found {len(records)} record(s).")
    write_csv(records, fieldnames, args.output)


if __name__ == "__main__":
    main()
