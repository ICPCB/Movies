"""Print live dataset stats and compare against config.

Run this after re-running the ingest pipeline to catch config drift.
"""
from pathlib import Path
import sys

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from src.config import (
    DATASET_LANGUAGE_FILTER,
    DATASET_MIN_VOTE_COUNT,
    DATASET_ROW_COUNT,
    DATASET_SOURCE,
)


def main() -> int:
    csv_path = Path("data/movies_clean.csv")
    if not csv_path.exists():
        print(f"ERROR: {csv_path} not found. Run 01.clean_data.py first.")
        return 1

    df = pd.read_csv(csv_path)
    actual_rows = len(df)
    min_vote_count = df["vote_count"].min() if "vote_count" in df.columns else None
    row_drift = actual_rows != DATASET_ROW_COUNT
    vote_drift = min_vote_count is not None and min_vote_count < DATASET_MIN_VOTE_COUNT

    print(f"Dataset source:                 {DATASET_SOURCE}")
    print(f"Language filter:                {DATASET_LANGUAGE_FILTER}")
    print(f"Config DATASET_ROW_COUNT:       {DATASET_ROW_COUNT}")
    print(f"Actual rows in CSV:             {actual_rows}")
    print(f"Config DATASET_MIN_VOTE_COUNT:  {DATASET_MIN_VOTE_COUNT}")
    print(f"Actual min vote_count:          {min_vote_count}")

    if row_drift:
        print(f"DRIFT: update DATASET_ROW_COUNT to {actual_rows}")
    if vote_drift:
        print("DRIFT: CSV contains rows below DATASET_MIN_VOTE_COUNT")

    return 1 if row_drift or vote_drift else 0


if __name__ == "__main__":
    raise SystemExit(main())
