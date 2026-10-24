"""Create an auditable ingredient identity crosswalk from curated mappings.

This module deliberately does not claim that external URLs were queried. The
current crosswalk records the evidence declared in the existing curation files
and marks it for verification before it can support production graph edges.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def build_crosswalk(synonym_map_path: str | Path, canonical_path: str | Path, output_root: str | Path) -> dict[str, Path]:
    synonym_map = pd.read_csv(synonym_map_path, dtype=str, keep_default_na=False)
    canonical = pd.read_csv(canonical_path, dtype=str, keep_default_na=False)
    ids = canonical.set_index("canonical_name")["canonical_ingredient_id"].to_dict()
    statuses = canonical.set_index("canonical_name")["review_status"].to_dict()
    crosswalk = synonym_map.copy()
    crosswalk["canonical_ingredient_id"] = crosswalk["canonical_ingredient"].map(ids).fillna("")
    crosswalk["verification_status"] = crosswalk.apply(_verification_status, axis=1)
    crosswalk["canonical_review_status"] = crosswalk["canonical_ingredient"].map(statuses).fillna("")
    crosswalk["review_date"] = ""
    crosswalk["external_identifier"] = ""
    crosswalk["review_notes"] = crosswalk.apply(_review_note, axis=1)
    columns = [
        "canonical_ingredient_id", "canonical_ingredient", "raw_ingredient", "mapping_type",
        "verification_status", "evidence_source", "evidence_url", "external_identifier",
        "canonical_review_status", "review_notes", "review_date",
    ]
    crosswalk = crosswalk[columns]
    root = Path(output_root)
    curated = root / "curated"
    review = root / "review"
    curated.mkdir(parents=True, exist_ok=True)
    review.mkdir(parents=True, exist_ok=True)
    crosswalk_path = curated / "ingredient_reference_crosswalk.csv"
    crosswalk.to_csv(crosswalk_path, index=False)
    review_path = review / "ingredient_identity_review_queue.csv"
    crosswalk[crosswalk["verification_status"] != "DECLARED_MAPPING_UNVERIFIED"].to_csv(review_path, index=False)
    report_path = root.parent / "reports" / "ingredient_identity_validation_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_report(crosswalk), encoding="utf-8")
    return {"crosswalk": crosswalk_path, "review": review_path, "report": report_path}


def _verification_status(row: pd.Series) -> str:
    if not row["canonical_ingredient_id"]:
        return "MISSING_CANONICAL_ID"
    if row["decision_status"].strip().lower() != "auto_approved":
        return "REVIEW_REQUIRED"
    return "DECLARED_MAPPING_UNVERIFIED"


def _review_note(row: pd.Series) -> str:
    if row["verification_status"] == "DECLARED_MAPPING_UNVERIFIED":
        return "Configured evidence claim retained; source was not queried in this run."
    return row.get("notes", "")


def _report(crosswalk: pd.DataFrame) -> str:
    counts = crosswalk["verification_status"].value_counts().to_dict()
    return "\n".join([
        "# Ingredient Identity Validation Report", "",
        "This report records the current curation crosswalk. It does not certify external evidence: no external source was queried during this run.", "",
        f"- Crosswalk rows: {len(crosswalk):,}",
        f"- Declared auto mappings not externally verified: {counts.get('DECLARED_MAPPING_UNVERIFIED', 0):,}",
        f"- Review-required mappings: {counts.get('REVIEW_REQUIRED', 0):,}",
        f"- Missing canonical IDs: {counts.get('MISSING_CANONICAL_ID', 0):,}", "",
        "## Gate", "",
        "Only mappings with an actual inspected authoritative reference and a recorded review decision may be promoted to verified. The current crosswalk remains unsuitable as sole evidence for clinical interaction claims.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ingredient identity crosswalk.")
    parser.add_argument("--synonyms", default="config/ingredient_synonym_map.csv")
    parser.add_argument("--canonical", default="config/canonical_ingredients.csv")
    parser.add_argument("--output-root", default="data")
    args = parser.parse_args()
    for name, path in build_crosswalk(args.synonyms, args.canonical, args.output_root).items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())