"""Stage 0 – Load and validate the raw CSV.

The source file is NEVER written to; a stable ``source_row_index``
(0-based integer matching the original CSV body row) is added as the
first column before any other processing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

# ── Expected schema ──────────────────────────────────────────────────────────
REQUIRED_COLUMNS: List[str] = [
    "commercial_name_en",
    "commercial_name_ar",
    "scientific_name",
    "manufacturer",
    "drug_class",
    "route",
    "price_egp",
]

EXPECTED_DTYPES: Dict[str, str] = {
    "commercial_name_en": "object",
    "commercial_name_ar": "object",
    "scientific_name": "object",
    "manufacturer": "object",
    "drug_class": "object",
    "route": "object",
    "price_egp": "float64",
}


class SchemaError(ValueError):
    """Raised when the loaded CSV does not match the expected schema."""


def load_raw(csv_path: str | Path) -> pd.DataFrame:
    """Load the raw CSV and assign a stable ``source_row_index``.

    Args:
        csv_path: Path to the Egyptian-drugs CSV (read-only; never written).

    Returns:
        DataFrame with an added ``source_row_index`` column (int64) and
        all original columns unchanged.

    Raises:
        FileNotFoundError: If ``csv_path`` does not exist.
        SchemaError: If required columns are missing or ``price_egp`` is
            not numeric.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    logger.info("Loading raw CSV: %s", csv_path)
    df = pd.read_csv(csv_path, dtype={"price_egp": "float64"})

    # Assign stable row identifier BEFORE any transformation
    df.insert(0, "source_row_index", range(len(df)))

    _validate_schema(df)

    logger.info("Loaded %d rows, %d columns.", len(df), len(df.columns))
    return df


def _validate_schema(df: pd.DataFrame) -> None:
    """Assert required columns exist and price_egp is numeric.

    Args:
        df: DataFrame to validate.

    Raises:
        SchemaError: On any schema violation.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise SchemaError(f"Missing required columns: {missing}")

    if not pd.api.types.is_numeric_dtype(df["price_egp"]):
        raise SchemaError("Column 'price_egp' is not numeric.")

    logger.info("Schema validation passed.")


def profile_raw(df: pd.DataFrame) -> Dict:
    """Generate a lightweight profiling summary of the raw DataFrame.

    Args:
        df: Raw DataFrame (with ``source_row_index`` already added).

    Returns:
        Dictionary suitable for serialisation into the DQ report.
    """
    profile: Dict = {
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": {},
    }

    for col in REQUIRED_COLUMNS:
        s = df[col]
        col_info: Dict = {
            "dtype": str(s.dtype),
            "null_count": int(s.isna().sum()),
            "null_pct": round(float(s.isna().mean() * 100), 2),
            "unique_count": int(s.nunique(dropna=True)),
        }
        if pd.api.types.is_numeric_dtype(s):
            col_info.update(
                {
                    "min": float(s.min()),
                    "max": float(s.max()),
                    "mean": round(float(s.mean()), 4),
                    "median": float(s.median()),
                    "p25": float(s.quantile(0.25)),
                    "p75": float(s.quantile(0.75)),
                }
            )
        else:
            sample = s.dropna().head(3).tolist()
            col_info["sample_values"] = sample
        profile["columns"][col] = col_info

    return profile
