"""Stage 6 – Ingredient-token inventory and review queue.

Responsibilities
----------------
* Build a flat table of (source_row_index, token_position, raw_token, …)
  from the list of ``ParseResult`` objects produced by Stage 5.
* Count raw-token frequencies.
* Build a review queue: tokens that are ambiguous, have embedded doses,
  carry parenthetical synonyms, or come from flagged parse results.

Nothing here attempts canonical name resolution.  That is intentional:
deduplication and synonym mapping require manual curation and an external
authority list (e.g. WHO INN) before they can be trusted.
"""

from __future__ import annotations

import logging
from typing import List

import pandas as pd

from .ingredient_parser import (
    FLAG_EMBEDDED_DOSE,
    FLAG_EQUALS_AMBIGUOUS,
    FLAG_MISSING,
    FLAG_PARENTHETICAL,
    FLAG_PARSE_ERROR,
    FLAG_SLASH_AMBIGUOUS,
    FLAG_TRUNCATED,
    ParseResult,
)

logger = logging.getLogger(__name__)

# Flags that automatically send a token to the review queue
_REVIEW_FLAGS = {
    FLAG_EMBEDDED_DOSE,
    FLAG_EQUALS_AMBIGUOUS,
    FLAG_SLASH_AMBIGUOUS,
    FLAG_PARENTHETICAL,
    FLAG_PARSE_ERROR,
    FLAG_TRUNCATED,
}

# Record-level flags that put ALL tokens of that record into the review queue
_RECORD_REVIEW_FLAGS = {
    FLAG_EQUALS_AMBIGUOUS,
    FLAG_TRUNCATED,
    FLAG_PARSE_ERROR,
}


def build_token_table(parse_results: List[ParseResult]) -> pd.DataFrame:
    """Build a flat per-token DataFrame from parsed results.

    One row per (product, token-position) pair.  Records with no tokens
    (missing or empty ``scientific_name``) produce zero rows here; they
    are captured in the audit table instead.

    Columns
    -------
    source_row_index : int
    token_position : int
        1-based position within the combination.
    raw_token : str
    name_stripped : str
        Token with heuristic dose expression removed.  NOT authoritative.
    dose_candidate : str | NaN
    parenthetical_content : str | NaN
    separator_detected : str
        The separator used for this record's split.
    record_flags : str
        Pipe-joined record-level flags from the ParseResult.
    token_flags : str
        Pipe-joined token-level flags from the IngredientToken.
    requires_review : bool
        True when any record or token flag triggers review.

    Args:
        parse_results: Output of ``ingredient_parser.parse_dataframe()``.

    Returns:
        DataFrame with one row per ingredient token.
    """
    rows = []

    for pr in parse_results:
        record_flags_str = "|".join(pr.flags) if pr.flags else ""
        record_needs_review = bool(_RECORD_REVIEW_FLAGS & set(pr.flags))

        for tok in pr.tokens:
            tok_flags_str = "|".join(tok.flags) if tok.flags else ""
            tok_needs_review = bool(_REVIEW_FLAGS & set(tok.flags))

            rows.append(
                {
                    "source_row_index": pr.source_row_index,
                    "token_position": tok.position,
                    "raw_token": tok.raw_token,
                    "name_stripped": tok.name_stripped,
                    "dose_candidate": tok.dose_candidate,
                    "parenthetical_content": tok.parenthetical_content,
                    "separator_detected": pr.separator_detected,
                    "record_flags": record_flags_str,
                    "token_flags": tok_flags_str,
                    "requires_review": record_needs_review or tok_needs_review,
                }
            )

    token_table = pd.DataFrame(rows)
    if token_table.empty:
        # Return typed empty frame so downstream code is safe
        token_table = pd.DataFrame(
            columns=[
                "source_row_index", "token_position", "raw_token",
                "name_stripped", "dose_candidate", "parenthetical_content",
                "separator_detected", "record_flags", "token_flags",
                "requires_review",
            ]
        )

    logger.info("Token table: %d rows from %d parse results.", len(token_table), len(parse_results))
    return token_table


def build_frequency_report(token_table: pd.DataFrame) -> pd.DataFrame:
    """Count occurrences of each raw token, sorted by frequency descending.

    Args:
        token_table: Output of ``build_token_table()``.

    Returns:
        DataFrame with columns: raw_token, occurrence_count,
        product_count (distinct source_row_index), pct_of_total_tokens,
        has_embedded_dose, has_parenthetical.
    """
    if token_table.empty:
        return pd.DataFrame(
            columns=[
                "raw_token", "occurrence_count", "product_count",
                "pct_of_total_tokens", "has_embedded_dose", "has_parenthetical",
            ]
        )

    total = len(token_table)

    freq = (
        token_table.groupby("raw_token", sort=False)
        .agg(
            occurrence_count=("raw_token", "size"),
            product_count=("source_row_index", "nunique"),
            has_embedded_dose=("dose_candidate", lambda s: s.notna().any()),
            has_parenthetical=("parenthetical_content", lambda s: s.notna().any()),
        )
        .reset_index()
        .sort_values("occurrence_count", ascending=False)
        .reset_index(drop=True)
    )

    freq["pct_of_total_tokens"] = (freq["occurrence_count"] / total * 100).round(3)
    logger.info(
        "Frequency report: %d unique raw tokens across %d total token occurrences.",
        len(freq),
        total,
    )
    return freq


def build_review_queue(token_table: pd.DataFrame) -> pd.DataFrame:
    """Extract tokens that need human review.

    A token enters the review queue when:
    * It has an embedded dose candidate (cannot be used as an ingredient
      name without confirmation that the dose was stripped correctly).
    * It has parenthetical content (synonym, IUPAC name, or parse error).
    * Its record carries EQUALS_AMBIGUOUS, TRUNCATED_LIST, or PARSE_ERROR.
    * Its record used a SLASH separator (SLASH_AMBIGUOUS).

    One row per *unique* raw_token in the review set, with aggregated
    counts and the set of flags observed across all occurrences.

    Args:
        token_table: Output of ``build_token_table()``.

    Returns:
        DataFrame sorted by occurrence_count descending.
    """
    if token_table.empty:
        return pd.DataFrame(
            columns=[
                "raw_token", "occurrence_count", "product_count",
                "all_flags", "review_reason_summary",
            ]
        )

    review_rows = token_table[token_table["requires_review"]].copy()

    if review_rows.empty:
        logger.info("Review queue is empty – no ambiguous tokens found.")
        return pd.DataFrame(
            columns=[
                "raw_token", "occurrence_count", "product_count",
                "all_flags", "review_reason_summary",
            ]
        )

    def _agg_flags(series: "pd.Series") -> str:  # noqa: F821
        all_f: set = set()
        for v in series:
            if v:
                all_f.update(v.split("|"))
        return "|".join(sorted(all_f)) if all_f else ""

    queue = (
        review_rows.groupby("raw_token", sort=False)
        .agg(
            occurrence_count=("raw_token", "size"),
            product_count=("source_row_index", "nunique"),
            all_record_flags=("record_flags", _agg_flags),
            all_token_flags=("token_flags", _agg_flags),
        )
        .reset_index()
        .sort_values("occurrence_count", ascending=False)
        .reset_index(drop=True)
    )

    # Build a human-readable reason summary
    reasons = []
    for _, row in queue.iterrows():
        parts = []
        combined = set((row["all_record_flags"] + "|" + row["all_token_flags"]).split("|")) - {""}
        if FLAG_EMBEDDED_DOSE in combined:
            parts.append("embedded-dose")
        if FLAG_PARENTHETICAL in combined:
            parts.append("parenthetical-synonym")
        if FLAG_EQUALS_AMBIGUOUS in combined:
            parts.append("equals-ambiguous")
        if FLAG_SLASH_AMBIGUOUS in combined:
            parts.append("slash-ambiguous")
        if FLAG_TRUNCATED in combined:
            parts.append("truncated-list")
        if FLAG_PARSE_ERROR in combined:
            parts.append("parse-error")
        reasons.append("; ".join(parts) if parts else "other")

    queue["review_reason_summary"] = reasons

    logger.info(
        "Review queue: %d unique tokens from %d token occurrences.",
        len(queue),
        len(review_rows),
    )
    return queue


def build_missing_sci_name_table(
    df: pd.DataFrame, parse_results: List[ParseResult]
) -> pd.DataFrame:
    """Return a table of records with missing or empty scientific names.

    Args:
        df: The processed DataFrame (must include ``source_row_index``
            and ``commercial_name_en``).
        parse_results: Output of ``parse_dataframe()``.

    Returns:
        DataFrame with source_row_index, commercial_name_en,
        drug_class (if present), and flag.
    """
    missing_idxs = {
        pr.source_row_index
        for pr in parse_results
        if FLAG_MISSING in pr.flags
    }

    if not missing_idxs:
        return pd.DataFrame(
            columns=["source_row_index", "commercial_name_en", "drug_class"]
        )

    cols = ["source_row_index", "commercial_name_en"]
    if "drug_class" in df.columns:
        cols.append("drug_class")

    missing_df = df[df["source_row_index"].isin(missing_idxs)][cols].copy()
    missing_df["flag"] = FLAG_MISSING
    return missing_df.reset_index(drop=True)
