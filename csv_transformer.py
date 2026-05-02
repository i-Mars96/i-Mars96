"""
csv_transformer.py — Filter, deduplicate, rename, and select columns in a CSV file.

Operations are always applied in a fixed order: filter → dedupe → rename → select.

Usage:
    python csv_transformer.py --input <FILE> [options]

Options:
    --input         Path to the source CSV file (required)
    --filter        pandas query() expression to filter rows, e.g. "age > 30 and country == 'CA'"
    --dedupe        Drop exact duplicate rows
    --dedupe-cols   Deduplicate on a subset of columns only (space-separated); requires --dedupe
    --rename        Rename columns as old:new pairs, e.g. --rename "Name:name" "Qty:quantity"
    --select        Keep only these columns in the given order (space-separated)
    --output        Output CSV file path (default: output.csv)

Examples:
    # Filter rows and write result
    python csv_transformer.py --input data.csv --filter "price > 100" --output filtered.csv

    # Full pipeline: filter, deduplicate on a key, rename a column, keep two columns
    python csv_transformer.py --input data.csv \\
        --filter "status == 'active'" \\
        --dedupe --dedupe-cols id \\
        --rename "product_name:name" \\
        --select id name price \\
        --output clean.csv
"""

import argparse
import sys

import pandas as pd


def load_csv(path: str) -> pd.DataFrame:
    if not __import__("pathlib").Path(path).exists():
        print(f"Error: file not found: '{path}'", file=sys.stderr)
        sys.exit(1)
    df = pd.read_csv(path)
    print(f"Loaded '{path}': {df.shape[0]} rows x {df.shape[1]} cols")
    return df


def parse_rename_definitions(rename_args: list[str]) -> dict[str, str]:
    """Parse 'old:new' pairs into a dict. Mirrors parse_field_definitions in attr_scraper.py."""
    mapping = {}
    for r in rename_args:
        parts = r.split(":", 1)
        if len(parts) != 2:
            print(f"Warning: skipping malformed rename definition '{r}' (expected old:new)")
            continue
        mapping[parts[0]] = parts[1]
    return mapping


def apply_filter(df: pd.DataFrame, expr: str) -> pd.DataFrame:
    before = len(df)
    try:
        df = df.query(expr)
    except Exception as e:
        print(f"Warning: filter expression failed ({e}). No filter applied.")
        return df
    print(f"Filter: {before} → {len(df)} rows")
    return df


def apply_deduplication(df: pd.DataFrame, subset: list[str] | None) -> pd.DataFrame:
    before = len(df)
    df = df.drop_duplicates(subset=subset if subset else None)
    print(f"Dedupe: removed {before - len(df)} duplicate row(s), {len(df)} remaining")
    return df


def apply_rename(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    unknown = [k for k in mapping if k not in df.columns]
    if unknown:
        print(f"Warning: rename skipped for unknown column(s): {unknown}")
    return df.rename(columns=mapping)


def apply_column_selection(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        print(f"Warning: column(s) not found and skipped: {missing}")
    keep = [c for c in columns if c in df.columns]
    return df[keep]


def write_csv(df: pd.DataFrame, output_path: str) -> None:
    df.to_csv(output_path, index=False)
    print(f"Wrote {len(df)} rows to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(description="CSV filter, dedupe, rename, and column selector")
    parser.add_argument("--input", required=True, help="Path to the source CSV file")
    parser.add_argument("--filter", dest="filter_expr", default=None,
                        help="pandas query() expression to filter rows")
    parser.add_argument("--dedupe", action="store_true",
                        help="Drop duplicate rows")
    parser.add_argument("--dedupe-cols", dest="dedupe_cols", nargs="+", default=None,
                        help="Deduplicate on these columns only (requires --dedupe)")
    parser.add_argument("--rename", nargs="+", default=None,
                        help="Rename columns as old:new pairs")
    parser.add_argument("--select", nargs="+", default=None,
                        help="Keep only these columns in the given order")
    parser.add_argument("--output", default="output.csv",
                        help="Output CSV path (default: output.csv)")
    args = parser.parse_args()

    df = load_csv(args.input)

    if args.filter_expr:
        df = apply_filter(df, args.filter_expr)

    if args.dedupe:
        df = apply_deduplication(df, args.dedupe_cols)

    if args.rename:
        mapping = parse_rename_definitions(args.rename)
        df = apply_rename(df, mapping)

    if args.select:
        df = apply_column_selection(df, args.select)

    print(f"Final shape: {df.shape[0]} rows x {df.shape[1]} cols")
    write_csv(df, args.output)


if __name__ == "__main__":
    main()
