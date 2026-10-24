"""Build a traceable product-level package from validated pipeline outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ACCEPTED_RESOLUTION_STATUSES = {"AUTO_CANONICAL", "EXACT_PASS_THROUGH"}


def build_product_package(
    products_csv: str | Path,
    canonicalized_tokens_csv: str | Path,
    canonical_ingredients_csv: str | Path,
    output_root: str | Path,
) -> dict[str, Path]:
    """Create Stage 3 clean, review, and audit tables without dropping source rows."""
    products = pd.read_csv(products_csv, dtype=str, keep_default_na=False)
    tokens = pd.read_csv(canonicalized_tokens_csv, dtype=str, keep_default_na=False)
    ingredients = pd.read_csv(canonical_ingredients_csv, dtype=str, keep_default_na=False)
    required_product = {"source_row_index", "commercial_name_en", "commercial_name_ar", "price_egp", "registration_status"}
    required_tokens = {"source_row_index", "token_position", "raw_token", "canonical_ingredient_id", "resolution_status"}
    missing_product = required_product - set(products.columns)
    missing_tokens = required_tokens - set(tokens.columns)
    if missing_product or missing_tokens:
        raise ValueError(f"Missing product columns={sorted(missing_product)}, token columns={sorted(missing_tokens)}")

    root = Path(output_root)
    clean_dir = root / "clean"
    review_dir = root / "review"
    audit_dir = root / "audit"
    for directory in (clean_dir, review_dir, audit_dir):
        directory.mkdir(parents=True, exist_ok=True)

    products["product_id"] = products["source_row_index"].map(lambda value: f"EGP-{int(value) + 1:05d}")
    products["commercial_name_en_clean"] = products["commercial_name_en"].map(_clean_text)
    products["commercial_name_ar_clean"] = products["commercial_name_ar"].map(_clean_text)
    products["price_egp"] = pd.to_numeric(products["price_egp"], errors="coerce")
    products["product_status"] = products["registration_status"].replace("", "UNKNOWN")
    products["source_dataset"] = "egyptian-drugs.csv"
    products["source_record_id"] = products["source_row_index"].map(lambda value: f"source-row-{int(value)}")
    products["data_quality_status"] = products.apply(_product_quality_status, axis=1)
    product_columns = [
        "product_id", "commercial_name_en", "commercial_name_ar", "commercial_name_en_clean", "commercial_name_ar_clean",
        "manufacturer", "drug_class", "route", "price_egp", "product_status", "source_dataset", "source_record_id",
        "source_row_index", "data_quality_status",
    ]
    products_path = clean_dir / "medicine_products.csv"
    products[product_columns].to_csv(products_path, index=False)

    aliases = pd.concat([
        products[["product_id", "commercial_name_en"]].rename(columns={"commercial_name_en": "alias_value"}).assign(alias_type="ENGLISH"),
        products[["product_id", "commercial_name_ar"]].rename(columns={"commercial_name_ar": "alias_value"}).assign(alias_type="ARABIC"),
    ], ignore_index=True)
    aliases = aliases[aliases["alias_value"].astype(str).str.strip() != ""]
    aliases["alias_value"] = aliases["alias_value"].map(_clean_text)
    aliases = aliases[["product_id", "alias_type", "alias_value"]].drop_duplicates()
    aliases_path = clean_dir / "product_aliases.csv"
    aliases.to_csv(aliases_path, index=False)

    product_id_by_source = products.set_index("source_row_index")["product_id"].to_dict()
    tokens["product_id"] = tokens["source_row_index"].map(product_id_by_source).fillna("")
    ingredient_status = ingredients.set_index("canonical_ingredient_id")["review_status"].to_dict()
    tokens["canonical_review_status"] = tokens["canonical_ingredient_id"].map(ingredient_status).fillna("")
    tokens["graph_eligible"] = (
        tokens["resolution_status"].isin(ACCEPTED_RESOLUTION_STATUSES)
        & tokens["canonical_ingredient_id"].ne("")
        & tokens["canonical_review_status"].eq("approved")
    )
    ingredient_columns = [
        "product_id", "source_row_index", "token_position", "raw_token", "name_stripped", "dose_candidate",
        "canonical_ingredient_id", "canonical_name", "resolution_status", "canonical_review_status", "graph_eligible",
    ]
    ingredient_columns = [column for column in ingredient_columns if column in tokens.columns]
    product_ingredients_path = clean_dir / "product_ingredients.csv"
    tokens[ingredient_columns].to_csv(product_ingredients_path, index=False)

    review = products[["product_id", "source_row_index", "commercial_name_en", "data_quality_status"]].copy()
    token_counts = tokens.groupby("source_row_index").agg(
        ingredient_token_count=("raw_token", "size"),
        unresolved_token_count=("resolution_status", lambda values: int((values == "UNRESOLVED").sum())),
        review_token_count=("resolution_status", lambda values: int((values == "NEEDS_REVIEW").sum())),
        graph_eligible_token_count=("graph_eligible", "sum"),
    ).reset_index()
    review = review.merge(token_counts, on="source_row_index", how="left").fillna(0)
    review = review[(review["ingredient_token_count"] == 0) | (review["unresolved_token_count"] > 0) | (review["review_token_count"] > 0)]
    review["review_reason"] = review.apply(lambda row: "MISSING_OR_EMPTY_SCIENTIFIC_NAME" if row["ingredient_token_count"] == 0 else "INGREDIENT_IDENTITY_REVIEW", axis=1)
    review_path = review_dir / "product_review_queue.csv"
    review.to_csv(review_path, index=False)

    audit = pd.DataFrame([
        {"metric": "source_product_rows", "value": len(products), "notes": "Every source row receives one deterministic product_id."},
        {"metric": "product_alias_rows", "value": len(aliases), "notes": "English and Arabic aliases are retained separately."},
        {"metric": "product_ingredient_rows", "value": len(tokens), "notes": "All parsed token relationships retained with resolution status."},
        {"metric": "graph_eligible_product_ingredient_rows", "value": int(tokens["graph_eligible"].sum()), "notes": "Only approved canonical identities and accepted mapping statuses."},
        {"metric": "products_requiring_review", "value": len(review), "notes": "Missing ingredient identity or unresolved/review mappings."},
    ])
    audit_path = audit_dir / "product_cleaning_audit.csv"
    audit.to_csv(audit_path, index=False)

    report_path = root.parent / "reports" / "product_cleaning_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(_report(products, aliases, tokens, review), encoding="utf-8")
    return {"products": products_path, "aliases": aliases_path, "product_ingredients": product_ingredients_path, "review": review_path, "audit": audit_path, "report": report_path}


def _clean_text(value: object) -> str:
    return " ".join(str(value).strip().split()) if value is not None else ""


def _product_quality_status(row: pd.Series) -> str:
    if not row["scientific_name"].strip():
        return "MISSING_SCIENTIFIC_NAME"
    if row.get("is_exact_duplicate", "False") == "True":
        return "EXACT_DUPLICATE_FLAGGED"
    if row.get("is_name_duplicate", "False") == "True":
        return "NAME_DUPLICATE_REVIEW"
    return "IDENTITY_REVIEW_REQUIRED"


def _report(products: pd.DataFrame, aliases: pd.DataFrame, tokens: pd.DataFrame, review: pd.DataFrame) -> str:
    eligible = int(tokens["graph_eligible"].sum())
    return "\n".join([
        "# Product Cleaning Report", "",
        "This package preserves every source product and token relationship. It does not merge products or infer missing ingredients.", "",
        f"- Source products: {len(products):,}",
        f"- Product aliases: {len(aliases):,}",
        f"- Product-ingredient token rows: {len(tokens):,}",
        f"- Graph-eligible token rows: {eligible:,}",
        f"- Products in review queue: {len(review):,}", "",
        "## Stable Identity", "",
        "`product_id` is derived from the immutable source row index as `EGP-00001` style identifiers. It is a source-record identifier, not an invented regulatory or registration number.", "",
        "## Graph Boundary", "",
        "All token rows remain in `data/clean/product_ingredients.csv`. The `graph_eligible` flag is false unless the canonical mapping is an accepted mapping or exact pass-through and the canonical ingredient is marked approved. Unresolved and review rows are never silently promoted.", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the traceable product cleaning package.")
    parser.add_argument("--products", required=True)
    parser.add_argument("--canonicalized", required=True)
    parser.add_argument("--ingredients", default="config/canonical_ingredients.csv")
    parser.add_argument("--output-root", default="data")
    args = parser.parse_args()
    for name, path in build_product_package(args.products, args.canonicalized, args.ingredients, args.output_root).items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())