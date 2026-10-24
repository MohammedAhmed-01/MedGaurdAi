"""Stage 5b – Active Ingredient Canonicalization.

Consumes:
    ingredient_token_table.csv   (from Stage 6 of the normalization pipeline)
    ingredient_synonym_map.csv   (manually curated + auto-generated mapping)
    canonical_ingredients.csv    (canonical reference table with stable IDs)

Produces:
    ingredient_token_canonicalized.csv
        One row per ingredient token, with resolved canonical_ingredient_id
        and canonical_name appended.

    canonicalization_report.json
        Summary statistics: how many tokens were auto-resolved, need review,
        are unresolved, or were rejected.

Design rules
------------
* Source tokens are NEVER modified.  All canonical assignments are new columns.
* Mapping uniqueness is validated: a raw token must not map to two different
  canonical IDs.  Conflicts raise a CanonicalizationConflictError.
* Manual decisions in the map file (decision_status != "auto_approved") are
  passed through as NEEDS_REVIEW; they are never silently promoted to canonical.
* Dose expressions, extra whitespace, and common abbreviations are normalised
  before map lookup so that "VITAMIN C 500 MG" matches "VITAMIN C".
* The module is deterministic and idempotent: re-running on the same inputs
  produces exactly the same outputs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# ── Resolution status codes ───────────────────────────────────────────────────
STATUS_AUTO = "AUTO_CANONICAL"          # auto_approved mapping found
STATUS_REVIEW = "NEEDS_REVIEW"          # mapping exists but needs_review
STATUS_UNRESOLVED = "UNRESOLVED"        # no mapping at all
STATUS_REJECTED = "REJECTED"            # decision_status == "rejected"
STATUS_EXACT = "EXACT_PASS_THROUGH"     # token already equals canonical form


class CanonicalizationConflictError(ValueError):
    """Raised when a raw token maps to two different canonical ingredients."""


# ── Normalisation helpers ─────────────────────────────────────────────────────

_DOSE_RE = re.compile(
    r"""
    \d[\d.,]*\s*             # number (no \b — catches "ZINC15MG")
    (?:MG|MCG|G\b|IU|%|ML\b|MMOL|MEQ|NANOMOL|MIU)  # unit
    """,
    re.IGNORECASE | re.VERBOSE,
)
_PAREN_RE = re.compile(r"\s*\([^)]*\)")
_WS_RE = re.compile(r"\s+")

# Accepted abbreviation expansions applied BEFORE map lookup
_ABBREV_MAP: Dict[str, str] = {
    r"\bVIT\b": "VITAMIN",
    r"\bHCL\b": "HYDROCHLORIDE",
    r"\bHCL\.\b": "HYDROCHLORIDE",
    r"\bAS\s+": "",            # "AS ASCORBIC ACID" → "ASCORBIC ACID"
}


def _normalise_for_lookup(raw: str) -> str:
    """Return a lookup key derived from *raw* by:
    1. Upper-casing.
    2. Stripping embedded dose expressions.
    3. Stripping parenthetical content.
    4. Expanding common abbreviations.
    5. Collapsing whitespace.

    The original *raw* value is never modified.
    """
    s = raw.upper().strip()
    s = _DOSE_RE.sub("", s)
    s = _PAREN_RE.sub("", s)
    for pattern, repl in _ABBREV_MAP.items():
        s = re.sub(pattern, repl, s, flags=re.IGNORECASE)
    s = _WS_RE.sub(" ", s).strip(" .,/")
    return s


# ── Mapping loader ────────────────────────────────────────────────────────────


def load_synonym_map(map_path: str | Path) -> pd.DataFrame:
    """Load and validate the synonym map CSV.

    Args:
        map_path: Path to ingredient_synonym_map.csv.

    Returns:
        DataFrame with required columns guaranteed present.

    Raises:
        FileNotFoundError: If the map file does not exist.
        ValueError: If required columns are missing.
    """
    map_path = Path(map_path)
    if not map_path.exists():
        raise FileNotFoundError(f"Synonym map not found: {map_path}")

    df = pd.read_csv(map_path, dtype=str, keep_default_na=False)
    required = {
        "raw_ingredient", "canonical_ingredient",
        "mapping_type", "decision_status",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Synonym map missing columns: {missing}")

    logger.info("Loaded synonym map: %d entries from %s", len(df), map_path)
    return df


def load_canonical_table(canon_path: str | Path) -> pd.DataFrame:
    """Load the canonical ingredients reference table.

    Args:
        canon_path: Path to canonical_ingredients.csv.

    Returns:
        DataFrame indexed by canonical_name (upper-cased).
    """
    canon_path = Path(canon_path)
    if not canon_path.exists():
        raise FileNotFoundError(f"Canonical table not found: {canon_path}")

    df = pd.read_csv(canon_path, dtype=str, keep_default_na=False)
    required = {"canonical_ingredient_id", "canonical_name"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Canonical table missing columns: {missing}")

    logger.info(
        "Loaded canonical table: %d ingredients from %s", len(df), canon_path
    )
    return df


# ── Map builder ───────────────────────────────────────────────────────────────


def build_lookup(
    synonym_map: pd.DataFrame,
    canonical_table: pd.DataFrame,
) -> Dict[str, Tuple[str, str, str]]:
    """Build a two-tier lookup dict for canonicalization.

    Tier 1 — exact_lookup: raw_ingredient.upper() → (canonical_name, id, status)
        Used first during resolution.  Parenthetical-specific entries such as
        ``VITAMIN B1 (BENFOTIAMINE)`` live here and are matched before their
        stripped form reaches the normalised tier.

    Tier 2 — norm_lookup: _normalise_for_lookup(raw_ingredient) → …
        Used as a fallback when the exact token is not in tier 1.
        Only entries whose normalised key is **unambiguous** (i.e. all rows
        with that key agree on the same canonical target) are placed here.
        Genuinely ambiguous normalised keys are excluded and flagged in the
        returned conflict_warnings list (they become UNRESOLVED at lookup time,
        which is correct — the reviewer must fix the source data).

    Args:
        synonym_map: Output of load_synonym_map().
        canonical_table: Output of load_canonical_table().

    Returns:
        Tuple of (exact_lookup, norm_lookup, conflict_warnings).
        Both lookups map a string key → (canonical_name, canonical_id, status).
        conflict_warnings is a list of human-readable conflict descriptions.

    Raises:
        CanonicalizationConflictError: When the exact_lookup itself has two
            rows for the same raw_ingredient pointing to different canonical
            targets (a genuine curation error, not a normalisation collision).
    """
    # Build canonical_name → id index
    canon_idx: Dict[str, str] = {
        row["canonical_name"].upper(): row["canonical_ingredient_id"]
        for _, row in canonical_table.iterrows()
    }

    exact_lookup: Dict[str, Tuple[str, str, str]] = {}
    norm_groups: Dict[str, list] = {}   # norm_key → list of (canon_name, id, status)
    exact_conflicts: list[str] = []

    for _, row in synonym_map.iterrows():
        raw_ingredient = row["raw_ingredient"].strip()
        exact_key = raw_ingredient.upper()
        norm_key = _normalise_for_lookup(raw_ingredient)
        canon_name = row["canonical_ingredient"].strip()
        status_raw = row["decision_status"].strip().lower()

        if status_raw == "auto_approved":
            status = STATUS_AUTO
        elif status_raw == "needs_review":
            status = STATUS_REVIEW
        elif status_raw == "rejected":
            status = STATUS_REJECTED
        else:
            status = STATUS_REVIEW

        canon_id = canon_idx.get(canon_name.upper(), "")
        entry = (canon_name, canon_id, status)

        # ── Tier 1: exact key ───────────────────────────────────────────────
        if exact_key in exact_lookup:
            existing = exact_lookup[exact_key][0]
            if existing.upper() != canon_name.upper():
                exact_conflicts.append(
                    f"Exact key '{exact_key}' maps to both "
                    f"'{existing}' and '{canon_name}' — fix the map file"
                )
        else:
            exact_lookup[exact_key] = entry

        # ── Tier 2: normalised key (collect for conflict check) ─────────────
        if norm_key not in norm_groups:
            norm_groups[norm_key] = []
        norm_groups[norm_key].append(entry)

    if exact_conflicts:
        raise CanonicalizationConflictError(
            "Exact mapping conflicts detected:\n" + "\n".join(exact_conflicts)
        )

    # Build norm_lookup: only insert when all entries for a key agree
    norm_lookup: Dict[str, Tuple[str, str, str]] = {}
    conflict_warnings: list[str] = []

    for norm_key, entries in norm_groups.items():
        canon_names_set = {e[0].upper() for e in entries}
        if len(canon_names_set) == 1:
            norm_lookup[norm_key] = entries[0]
        else:
            conflict_warnings.append(
                f"Normalised key '{norm_key}' maps to multiple canonicals "
                f"({', '.join(sorted(canon_names_set))}) — "
                f"will be UNRESOLVED unless exact match found"
            )

    if conflict_warnings:
        logger.warning(
            "%d normalised-key conflicts (these tokens will be UNRESOLVED "
            "unless an exact map entry exists):\n  %s",
            len(conflict_warnings),
            "\n  ".join(conflict_warnings),
        )

    logger.info(
        "Lookup built: %d exact entries, %d normalised entries, %d norm-conflicts",
        len(exact_lookup), len(norm_lookup), len(conflict_warnings),
    )
    # Return as a combined dict with a sentinel so canonicalize_token_table
    # can use the two-tier strategy.  We encode the tiers in a single dict
    # by wrapping them in a container object.
    return _LookupPair(exact_lookup, norm_lookup, conflict_warnings)


class _LookupPair:
    """Container for two-tier lookup dicts returned by build_lookup."""

    def __init__(
        self,
        exact: Dict[str, Tuple[str, str, str]],
        norm: Dict[str, Tuple[str, str, str]],
        conflicts: list,
    ):
        self.exact = exact
        self.norm = norm
        self.conflicts = conflicts

    # Make it usable in tests that call ``key in lookup``
    def __contains__(self, key: str) -> bool:
        return key in self.exact or key in self.norm

    def get(self, key: str) -> Optional[Tuple[str, str, str]]:
        return self.exact.get(key) or self.norm.get(key)


# ── Main canonicalization function ────────────────────────────────────────────


def canonicalize_token_table(
    token_table: pd.DataFrame,
    lookup: Dict[str, Tuple[str, str, str]],
) -> pd.DataFrame:
    """Apply canonical mappings to the ingredient token table.

    Added columns
    -------------
    normalised_lookup_key : str
        The key used for map lookup (dose-stripped, abbreviation-expanded).
    canonical_name : str
        Resolved canonical ingredient name, or empty string if unresolved.
    canonical_ingredient_id : str
        Stable canonical ID, or empty string.
    resolution_status : str
        One of AUTO_CANONICAL, NEEDS_REVIEW, UNRESOLVED, REJECTED,
        EXACT_PASS_THROUGH.

    Args:
        token_table: DataFrame with at least a 'raw_token' column.
        lookup: Output of build_lookup().

    Returns:
        token_table with four new columns appended.
    """
    df = token_table.copy()

    norm_keys, canon_names, canon_ids, statuses = [], [], [], []

    for raw in df["raw_token"]:
        raw_str = str(raw).strip() if pd.notna(raw) else ""
        if not raw_str:
            norm_keys.append("")
            canon_names.append("")
            canon_ids.append("")
            statuses.append(STATUS_UNRESOLVED)
            continue

        exact_key = raw_str.upper()
        norm_key = _normalise_for_lookup(raw_str)

        # Two-tier resolution: exact first, normalised as fallback
        if hasattr(lookup, 'exact'):
            # _LookupPair from build_lookup
            hit = lookup.exact.get(exact_key) or lookup.norm.get(norm_key)
        else:
            # Plain dict (used in unit tests with minimal fixtures)
            hit = lookup.get(exact_key) or lookup.get(norm_key)

        if hit:
            cname, cid, cstatus = hit
            if raw_str.upper() == cname.upper() and cstatus == STATUS_AUTO:
                cstatus = STATUS_EXACT
            norm_keys.append(norm_key)
            canon_names.append(cname)
            canon_ids.append(cid)
            statuses.append(cstatus)
        else:
            norm_keys.append(norm_key)
            canon_names.append("")
            canon_ids.append("")
            statuses.append(STATUS_UNRESOLVED)

    df["normalised_lookup_key"] = norm_keys
    df["canonical_name"] = canon_names
    df["canonical_ingredient_id"] = canon_ids
    df["resolution_status"] = statuses

    counts = pd.Series(statuses).value_counts().to_dict()
    logger.info("Canonicalization complete: %s", counts)
    return df


# ── Report builder ────────────────────────────────────────────────────────────


def build_canonicalization_report(
    canonicalized_table: pd.DataFrame,
    synonym_map: pd.DataFrame,
    canonical_table: pd.DataFrame,
) -> dict:
    """Assemble a summary report of canonicalization results.

    Args:
        canonicalized_table: Output of canonicalize_token_table().
        synonym_map: The loaded synonym map DataFrame.
        canonical_table: The canonical ingredients reference table.

    Returns:
        Dict suitable for JSON serialisation.
    """
    df = canonicalized_table
    status_counts = df["resolution_status"].value_counts().to_dict()
    total_tokens = len(df)

    auto_pct = round(
        status_counts.get(STATUS_AUTO, 0) / total_tokens * 100, 2
    ) if total_tokens else 0
    exact_pct = round(
        status_counts.get(STATUS_EXACT, 0) / total_tokens * 100, 2
    ) if total_tokens else 0
    review_pct = round(
        status_counts.get(STATUS_REVIEW, 0) / total_tokens * 100, 2
    ) if total_tokens else 0
    unresolved_pct = round(
        status_counts.get(STATUS_UNRESOLVED, 0) / total_tokens * 100, 2
    ) if total_tokens else 0

    # Top unresolved tokens by occurrence
    unresolved_df = (
        df[df["resolution_status"] == STATUS_UNRESOLVED]
        .groupby("raw_token")["source_row_index"]
        .nunique()
        .reset_index()
        .rename(columns={"source_row_index": "product_count"})
        .sort_values("product_count", ascending=False)
        .head(20)
    )
    top_unresolved = unresolved_df.to_dict("records")

    # Top NEEDS_REVIEW tokens
    review_df = (
        df[df["resolution_status"] == STATUS_REVIEW]
        .groupby(["raw_token", "canonical_name"])["source_row_index"]
        .nunique()
        .reset_index()
        .rename(columns={"source_row_index": "product_count"})
        .sort_values("product_count", ascending=False)
        .head(20)
    )
    top_review = review_df.to_dict("records")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_stage": "5b_canonicalization",
        "totals": {
            "total_token_occurrences": int(total_tokens),
            "unique_raw_tokens_in_table": int(df["raw_token"].nunique()),
            "canonical_entries_in_map": int(len(synonym_map)),
            "canonical_ingredients_in_reference": int(len(canonical_table)),
        },
        "resolution_status_counts": {k: int(v) for k, v in status_counts.items()},
        "resolution_pct": {
            STATUS_AUTO: auto_pct,
            STATUS_EXACT: exact_pct,
            STATUS_REVIEW: review_pct,
            STATUS_UNRESOLVED: unresolved_pct,
        },
        "top_unresolved_tokens": top_unresolved,
        "top_needs_review_tokens": top_review,
    }


# ── Pipeline runner ───────────────────────────────────────────────────────────


def run(
    token_table_path: str | Path,
    synonym_map_path: str | Path,
    canonical_table_path: str | Path,
    output_dir: str | Path,
    log_level: str = "INFO",
) -> dict:
    """Run the full canonicalization stage and write outputs.

    Args:
        token_table_path: Path to ingredient_token_table.csv.
        synonym_map_path: Path to ingredient_synonym_map.csv.
        canonical_table_path: Path to canonical_ingredients.csv.
        output_dir: Directory for output files.
        log_level: Python logging level.

    Returns:
        Dict of output file paths.
    """
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    token_table = pd.read_csv(token_table_path, dtype=str, low_memory=False)
    synonym_map = load_synonym_map(synonym_map_path)
    canonical_table = load_canonical_table(canonical_table_path)

    lookup = build_lookup(synonym_map, canonical_table)
    canon_table = canonicalize_token_table(token_table, lookup)

    report = build_canonicalization_report(canon_table, synonym_map, canonical_table)

    # Write outputs
    paths = {}

    p = out / "ingredient_token_canonicalized.csv"
    canon_table.to_csv(p, index=False)
    paths["ingredient_token_canonicalized"] = str(p)
    logger.info("Wrote %s (%d rows)", p.name, len(canon_table))

    p = out / "canonicalization_report.json"
    p.write_text(json.dumps(report, indent=2, default=str))
    paths["canonicalization_report"] = str(p)
    logger.info("Wrote %s", p.name)

    return paths
