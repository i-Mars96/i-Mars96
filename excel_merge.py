"""
excel_merge.py — General-purpose multi-file Excel merge and comparison tool.

Loads 2 or more Excel files into pandas DataFrames, chains outer merges across
all of them in order, summarizes what's unique to each source vs. shared, and
exports the final merged result to a new Excel file.

Generalizes the patterns from SuccesfulFarmingQC.py (2-file keyed merge) and
bayercounts.py (3-file chained merge).

Requirements:
    pip install pandas openpyxl

Usage:
    python excel_merge.py --files file1.xlsx file2.xlsx [file3.xlsx ...] [options]

Options:
    --files         Two or more Excel files to merge (required)
    --merge-key     Column name to merge on (optional; merges on all shared columns if omitted)
    --sheet         Sheet name or index to read from each file (default: 0, first sheet)
    --output        Output Excel file path (default: merged_output.xlsx)

Examples:
    # 2-file keyed merge (SuccesfulFarmingQC style)
    python excel_merge.py \\
        --files AdamsPullACT_ARC.xlsx IansPullAct_Arch_4.xlsx \\
        --merge-key BACID \\
        --output SuccesfulFarmDiff.xlsx

    # 3-file chained merge (bayercounts style)
    python excel_merge.py \\
        --files Sept.xlsx Oct.xlsx Nov.xlsx \\
        --output Merge.xlsx
"""

import argparse
import sys
from pathlib import Path

import pandas as pd


def load_files(file_paths: list[str], sheet) -> list[tuple[str, pd.DataFrame]]:
    """
    Read each Excel file into a DataFrame.
    Returns a list of (filename, DataFrame) tuples.
    """
    results = []
    for path in file_paths:
        df = pd.read_excel(path, sheet_name=sheet)
        print(f"Loaded '{Path(path).name}': {df.shape[0]} rows x {df.shape[1]} cols")
        results.append((Path(path).name, df))
    return results


def reset_indexes(named_dfs: list[tuple[str, pd.DataFrame]]) -> list[tuple[str, pd.DataFrame]]:
    """Reset the index on each DataFrame to ensure clean integer indexes before merging."""
    return [(name, df.reset_index(drop=True)) for name, df in named_dfs]


def merge_dataframes(
    named_dfs: list[tuple[str, pd.DataFrame]],
    merge_key: str | None,
) -> pd.DataFrame:
    """
    Chain outer merges across all DataFrames in order.
    Each merge step adds a _merge_N indicator column showing whether each row
    came from left_only, right_only, or both sources.
    """
    _, result = named_dfs[0]
    result = result.copy()

    for i, (name, df) in enumerate(named_dfs[1:], start=1):
        indicator_col = f"_merge_{i}"
        kwargs = {
            "how": "outer",
            "indicator": indicator_col,
        }
        if merge_key:
            kwargs["on"] = merge_key
        result = pd.merge(result, df, **kwargs)
        print(f"After merge {i} (+ '{name}'): {result.shape[0]} rows")

    return result


def compare_dataframes(merged: pd.DataFrame) -> dict:
    """
    Read the _merge_N indicator columns and summarize what's unique to each
    source vs. what's shared across all files. Returns a summary dict.
    """
    merge_cols = [c for c in merged.columns if c.startswith("_merge_")]
    summary = {}
    for col in merge_cols:
        counts = merged[col].value_counts().to_dict()
        summary[col] = {
            "left_only":  counts.get("left_only", 0),
            "right_only": counts.get("right_only", 0),
            "both":       counts.get("both", 0),
        }
    return summary


def export_to_excel(df: pd.DataFrame, output_path: str) -> None:
    """Write the final merged DataFrame to an Excel file."""
    df.to_excel(output_path, index=False)
    print(f"Exported {df.shape[0]} rows to '{output_path}'")


def main():
    parser = argparse.ArgumentParser(description="Multi-file Excel merge and comparison tool")
    parser.add_argument("--files", nargs="+", required=True,
                        help="Two or more Excel files to merge")
    parser.add_argument("--merge-key", dest="merge_key",
                        help="Column to merge on (optional)")
    parser.add_argument("--sheet", default=0,
                        help="Sheet name or index to read (default: 0)")
    parser.add_argument("--output", default="merged_output.xlsx",
                        help="Output file path (default: merged_output.xlsx)")
    args = parser.parse_args()

    if len(args.files) < 2:
        print("Error: provide at least 2 files to merge.", file=sys.stderr)
        sys.exit(1)

    named_dfs = load_files(args.files, args.sheet)
    named_dfs = reset_indexes(named_dfs)

    merged = merge_dataframes(named_dfs, args.merge_key)

    summary = compare_dataframes(merged)
    print("\n--- Comparison Summary ---")
    for merge_step, counts in summary.items():
        print(f"  {merge_step}: {counts['both']} shared | "
              f"{counts['left_only']} left-only | {counts['right_only']} right-only")

    print(f"\nTotal rows in merged result: {merged.shape[0]}")
    export_to_excel(merged, args.output)


if __name__ == "__main__":
    main()
