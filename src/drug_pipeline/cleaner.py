"""Stages 1–4 – Row-level cleaning, manufacturer parsing,
drug-class canonicalization, and route canonicalization.

Design principles
-----------------
* Original values are NEVER overwritten; every transformation adds a new
  column and keeps ``*_original`` or ``*_raw`` alongside it.
* Ambiguous cases are FLAGGED, not silently resolved.
* Mapping files (CSV) drive all controlled-vocabulary normalisations so
  curators can extend them without touching code.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ── Status-marker regex built from the config file ───────────────────────────
_STATUS_PATTERN = re.compile(
    r"\s*\((ILLEGAL IMPORT|WITHDRAWAL|CANCELLED|N/A|DISCONTINUED)\)\s*",
    re.IGNORECASE,
)

_STATUS_CODE_MAP = {
    "ILLEGAL IMPORT": "ILLEGAL_IMPORT",
    "WITHDRAWAL": "WITHDRAWN",
    "CANCELLED": "CANCELLED",
    "N/A": "NOT_APPLICABLE",
    "DISCONTINUED": "DISCONTINUED",
}


# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – Row-level cleaning
# ─────────────────────────────────────────────────────────────────────────────


def detect_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """Flag exact duplicate rows and duplicate commercial names.

    Does NOT drop anything — returns the input with two new boolean
    columns so the caller can decide what to do.

    Added columns
    -------------
    is_exact_duplicate : bool
        True if this row is an identical copy of a previous row (all
        REQUIRED_COLUMNS match).
    is_name_duplicate : bool
        True if ``commercial_name_en`` appears more than once in the
        dataset (all occurrences are flagged, including the first).

    Args:
        df: DataFrame with ``source_row_index`` present.

    Returns:
        DataFrame with two new flag columns appended.
    """
    key_cols = [
        "commercial_name_en",
        "commercial_name_ar",
        "scientific_name",
        "manufacturer",
        "drug_class",
        "route",
        "price_egp",
    ]
    available = [c for c in key_cols if c in df.columns]

    df = df.copy()
    df["is_exact_duplicate"] = df.duplicated(subset=available, keep="first")
    df["is_name_duplicate"] = df.duplicated(subset=["commercial_name_en"], keep=False)

    n_exact = df["is_exact_duplicate"].sum()
    n_name = df["is_name_duplicate"].sum()
    logger.info("Exact duplicate rows: %d", n_exact)
    logger.info("Rows sharing a commercial_name_en with another row: %d", n_name)
    return df


def extract_status_markers(df: pd.DataFrame) -> pd.DataFrame:
    """Detect registration-status markers in ``commercial_name_en``.

    The original ``commercial_name_en`` is preserved unchanged.
    Two new columns are added:

    registration_status : str | NaN
        Canonical status code (e.g. ``"ILLEGAL_IMPORT"``), or NaN if
        no marker was found.
    commercial_name_en_clean : str
        The commercial name with the status marker removed and
        surrounding whitespace stripped.  Identical to
        ``commercial_name_en`` when no marker is present.

    Args:
        df: DataFrame at any stage after loading.

    Returns:
        DataFrame with two new columns.
    """
    df = df.copy()

    statuses: list[Optional[str]] = []
    clean_names: list[str] = []

    for name in df["commercial_name_en"]:
        m = _STATUS_PATTERN.search(str(name))
        if m:
            code = _STATUS_CODE_MAP.get(m.group(1).upper(), m.group(1).upper())
            statuses.append(code)
            clean_names.append(_STATUS_PATTERN.sub("", name).strip())
        else:
            statuses.append(None)
            clean_names.append(str(name).strip())

    df["registration_status"] = statuses
    df["commercial_name_en_clean"] = clean_names

    n_flagged = sum(1 for s in statuses if s is not None)
    logger.info("Records with registration-status marker: %d", n_flagged)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – Manufacturer parsing
# ─────────────────────────────────────────────────────────────────────────────


def parse_manufacturer(df: pd.DataFrame) -> pd.DataFrame:
    """Split ``manufacturer`` on ' > ' into proposed local and distributor.

    The ``>`` notation is ASSUMED to mean ``local_manufacturer > distributor``
    based on dataset conventions, but this interpretation is not verified for
    every record.  All records using this notation are flagged.

    Added columns
    -------------
    manufacturer_local : str | NaN
        Left side of ` > ` split, or the full value when no ` > ` is present.
    manufacturer_distributor : str | NaN
        Right side of ` > ` split; NaN when there is no ` > `.
    manufacturer_parse_flag : str
        ``"SPLIT"``  – split was applied.
        ``"PLAIN"``  – no ``>`` present; taken as-is.
        ``"MULTI_SPLIT"`` – more than one ` > ` found; only first split kept;
                           flagged for manual review.
        ``"MISSING"`` – original value was null.

    Args:
        df: DataFrame after Stage 1.

    Returns:
        DataFrame with three new columns.
    """
    df = df.copy()

    local_list: list[Optional[str]] = []
    dist_list: list[Optional[str]] = []
    flag_list: list[str] = []

    for raw in df["manufacturer"]:
        if pd.isna(raw) or str(raw).strip() == "":
            local_list.append(None)
            dist_list.append(None)
            flag_list.append("MISSING")
            continue

        raw_str = str(raw).strip()
        parts = raw_str.split(" > ")

        if len(parts) == 1:
            local_list.append(parts[0])
            dist_list.append(None)
            flag_list.append("PLAIN")
        elif len(parts) == 2:
            local_list.append(parts[0].strip())
            dist_list.append(parts[1].strip())
            flag_list.append("SPLIT")
        else:
            # More than one ` > `: keep first split, flag for review
            local_list.append(parts[0].strip())
            dist_list.append(" > ".join(parts[1:]).strip())
            flag_list.append("MULTI_SPLIT")

    df["manufacturer_local"] = local_list
    df["manufacturer_distributor"] = dist_list
    df["manufacturer_parse_flag"] = flag_list

    logger.info(
        "Manufacturer parsing: PLAIN=%d  SPLIT=%d  MULTI_SPLIT=%d  MISSING=%d",
        flag_list.count("PLAIN"),
        flag_list.count("SPLIT"),
        flag_list.count("MULTI_SPLIT"),
        flag_list.count("MISSING"),
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 – Drug-class canonicalization
# ─────────────────────────────────────────────────────────────────────────────


def canonicalize_drug_class(df: pd.DataFrame, map_path: str | Path) -> pd.DataFrame:
    """Map raw ``drug_class`` values to canonical equivalents.

    Values not found in the map file are passed through unchanged with
    ``drug_class_reviewed = False`` so the review queue can surface them.

    Added columns
    -------------
    drug_class_canonical : str | NaN
        Normalised class, or NaN when both original and mapping are null.
    drug_class_reviewed : bool
        True only when the mapping file explicitly provides a canonical form.

    Args:
        df: DataFrame after Stage 2.
        map_path: Path to ``config/drug_class_map.csv``.

    Returns:
        DataFrame with two new columns.
    """
    map_path = Path(map_path)
    class_map: Dict[str, Optional[str]] = {}

    if map_path.exists():
        cmap = pd.read_csv(map_path, dtype=str, keep_default_na=False)
        for _, row in cmap.iterrows():
            raw_val = row["raw_value"].strip()
            can_val = row["canonical_value"].strip() if row["canonical_value"].strip() else None
            class_map[raw_val] = can_val
        logger.info("Loaded %d drug-class mappings from %s", len(class_map), map_path)
    else:
        logger.warning("Drug-class map not found: %s – skipping canonicalization.", map_path)

    df = df.copy()
    canonical: list[Optional[str]] = []
    reviewed: list[bool] = []

    for raw in df["drug_class"]:
        raw_str = str(raw).strip() if pd.notna(raw) else ""
        if raw_str in class_map:
            canonical.append(class_map[raw_str])
            reviewed.append(True)
        elif raw_str == "" or pd.isna(raw):
            canonical.append(None)
            reviewed.append(False)
        else:
            # Not in map: pass through, mark unreviewed
            canonical.append(raw_str)
            reviewed.append(False)

    df["drug_class_canonical"] = canonical
    df["drug_class_reviewed"] = reviewed

    n_rev = sum(reviewed)
    n_unrev = len(reviewed) - n_rev
    logger.info("Drug-class: reviewed=%d  unreviewed=%d", n_rev, n_unrev)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Stage 4 – Route canonicalization
# ─────────────────────────────────────────────────────────────────────────────


def canonicalize_route(df: pd.DataFrame, map_path: str | Path) -> pd.DataFrame:
    """Map raw ``route`` values to canonical equivalents.

    ``UNKNOWN`` maps to NaN (no route information available).
    ``SPRAY`` maps to ``SPRAY.UNSPECIFIED`` and is flagged for context review.

    Added columns
    -------------
    route_canonical : str | NaN
    route_needs_review : bool

    Args:
        df: DataFrame after Stage 3.
        map_path: Path to ``config/route_map.csv``.

    Returns:
        DataFrame with two new columns.
    """
    map_path = Path(map_path)
    route_map: Dict[str, Optional[str]] = {}
    review_set: set[str] = set()

    if map_path.exists():
        rmap = pd.read_csv(map_path, dtype=str, keep_default_na=False)
        for _, row in rmap.iterrows():
            raw_val = row["raw_value"].strip()
            can_val = row["canonical_value"].strip() if row["canonical_value"].strip() else None
            route_map[raw_val] = can_val
            if "review" in row.get("notes", "").lower() or can_val == "SPRAY.UNSPECIFIED":
                review_set.add(raw_val)
        logger.info("Loaded %d route mappings from %s", len(route_map), map_path)
    else:
        logger.warning("Route map not found: %s – skipping canonicalization.", map_path)

    df = df.copy()
    canonical: list[Optional[str]] = []
    needs_review: list[bool] = []

    for raw in df["route"]:
        raw_str = str(raw).strip() if pd.notna(raw) else ""
        if raw_str in route_map:
            canonical.append(route_map[raw_str])
            needs_review.append(raw_str in review_set)
        else:
            canonical.append(raw_str if raw_str else None)
            needs_review.append(True)  # unseen value – flag it

    df["route_canonical"] = canonical
    df["route_needs_review"] = needs_review

    logger.info(
        "Route: %d records need context review",
        sum(needs_review),
    )
    return df
