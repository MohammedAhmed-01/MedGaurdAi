"""Pipeline orchestrator.

Runs Stages 0–7 in order and writes all outputs.

Usage (from project root)::

    python run_pipeline.py --source /path/to/egyptian-drugs.csv \\
                           --output outputs/ \\
                           --config config/

Each stage logs its progress; the pipeline fails fast on schema errors
and continues with flags for data-quality issues.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

from .cleaner import (
    canonicalize_drug_class,
    canonicalize_route,
    detect_duplicates,
    extract_status_markers,
    parse_manufacturer,
)
from .ingredient_parser import parse_dataframe
from .inventory import (
    build_frequency_report,
    build_missing_sci_name_table,
    build_review_queue,
    build_token_table,
)
from .loader import load_raw, profile_raw
from .reporter import build_dq_stats, write_outputs

logger = logging.getLogger(__name__)


def run(
    source_csv: str | Path,
    output_dir: str | Path,
    config_dir: str | Path,
    log_level: str = "INFO",
) -> dict:
    """Execute the full pipeline and write all outputs.

    Args:
        source_csv: Path to the raw Egyptian-drugs CSV (read-only).
        output_dir: Directory where output files are written.
        config_dir: Directory containing mapping CSV files.
        log_level: Python logging level string.

    Returns:
        Dictionary of output file paths (from ``write_outputs``).
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    config_dir = Path(config_dir)
    logger.info("=" * 60)
    logger.info("Egyptian Drug Normalization Pipeline  v0.1.0")
    logger.info("=" * 60)

    # ── Stage 0: Load & validate ──────────────────────────────────────────────
    logger.info("[Stage 0] Loading and validating source CSV …")
    df = load_raw(source_csv)
    df_raw_snapshot = df.copy()   # immutable reference for DQ stats
    raw_profile = profile_raw(df)

    # ── Stage 1: Row-level cleaning ───────────────────────────────────────────
    logger.info("[Stage 1] Row-level cleaning …")
    df = detect_duplicates(df)
    df = extract_status_markers(df)

    # ── Stage 2: Manufacturer parsing ─────────────────────────────────────────
    logger.info("[Stage 2] Manufacturer parsing …")
    df = parse_manufacturer(df)

    # ── Stage 3: Drug-class canonicalization ──────────────────────────────────
    logger.info("[Stage 3] Drug-class canonicalization …")
    df = canonicalize_drug_class(df, config_dir / "drug_class_map.csv")

    # ── Stage 4: Route canonicalization ───────────────────────────────────────
    logger.info("[Stage 4] Route canonicalization …")
    df = canonicalize_route(df, config_dir / "route_map.csv")

    # ── Stage 5: scientific_name structural parsing ───────────────────────────
    logger.info("[Stage 5] Parsing scientific_name …")
    parse_results = parse_dataframe(df)

    # ── Stage 6: Token inventory ──────────────────────────────────────────────
    logger.info("[Stage 6] Building ingredient-token inventory …")
    token_table = build_token_table(parse_results)
    freq_report = build_frequency_report(token_table)
    review_queue = build_review_queue(token_table)
    missing_sci_table = build_missing_sci_name_table(df, parse_results)

    # ── Stage 7: DQ report & output writing ───────────────────────────────────
    logger.info("[Stage 7] Generating data-quality report …")
    dq_stats = build_dq_stats(
        df_raw=df_raw_snapshot,
        df_clean=df,
        parse_results=parse_results,
        token_table=token_table,
        freq_report=freq_report,
        review_queue=review_queue,
        raw_profile=raw_profile,
    )

    output_paths = write_outputs(
        df_clean=df,
        token_table=token_table,
        freq_report=freq_report,
        review_queue=review_queue,
        missing_sci_table=missing_sci_table,
        dq_stats=dq_stats,
        output_dir=output_dir,
    )

    logger.info("Pipeline complete.  Outputs written to: %s", Path(output_dir).resolve())
    return output_paths
