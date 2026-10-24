"""Offline, evidence-gated product interaction lookup.

The detector only reports interactions present in a caller-supplied evidence
file. It never infers an interaction from names, classes, or model knowledge.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_INTERACTION_COLUMNS = {
    "interaction_id", "ingredient_a_id", "ingredient_b_id", "source_name", "source_url",
}


def check_interactions(
    medicine_inputs: list[str],
    sources: list[str] | None = None,
    *,
    products_path: str | Path = "data/clean/medicine_products.csv",
    aliases_path: str | Path = "data/clean/product_aliases.csv",
    ingredients_path: str | Path = "data/clean/product_ingredients.csv",
    interactions_path: str | Path | None = "data/interactions/ingredient_interactions.csv",
) -> dict[str, Any]:
    """Resolve medicines and compare all cross-medicine ingredient pairs.

    ``sources`` is an optional allow-list of source names. A missing evidence
    file returns ``SOURCE_QUERY_FAILED``; an existing file with no pair match
    returns ``NO_MATCH_FOUND_IN_QUERIED_SOURCES`` and never ``SAFE``.
    """
    if not medicine_inputs:
        return {"status": "INSUFFICIENT_EVIDENCE", "resolved_medicines": [], "matches": [], "unresolved_pairs": [], "coverage": {}}
    if interactions_path is None or not Path(interactions_path).exists():
        return {"status": "SOURCE_QUERY_FAILED", "resolved_medicines": [], "matches": [], "unresolved_pairs": [], "coverage": {"reason": "interaction evidence file is missing"}}

    try:
        products = pd.read_csv(products_path, dtype=str, keep_default_na=False)
        aliases = pd.read_csv(aliases_path, dtype=str, keep_default_na=False)
        product_ingredients = pd.read_csv(ingredients_path, dtype=str, keep_default_na=False)
        interactions = pd.read_csv(interactions_path, dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError, ValueError) as exc:
        return {"status": "SOURCE_QUERY_FAILED", "resolved_medicines": [], "matches": [], "unresolved_pairs": [], "coverage": {"reason": str(exc)}}
    missing = REQUIRED_INTERACTION_COLUMNS - set(interactions.columns)
    if missing:
        return {"status": "SOURCE_QUERY_FAILED", "resolved_medicines": [], "matches": [], "unresolved_pairs": [], "coverage": {"reason": f"missing interaction columns: {sorted(missing)}"}}

    alias_index: dict[str, set[str]] = {}
    for row in aliases.itertuples(index=False):
        alias_index.setdefault(str(row.alias_value).strip().casefold(), set()).add(row.product_id)
    product_index = products.set_index("product_id").to_dict("index")
    ingredient_index = product_ingredients[product_ingredients["graph_eligible"].astype(str).str.lower() == "true"].groupby("product_id")["canonical_ingredient_id"].apply(lambda values: sorted(set(values))).to_dict()

    resolved = []
    unresolved = []
    for medicine in medicine_inputs:
        key = str(medicine).strip().casefold()
        product_ids = alias_index.get(key, set())
        if len(product_ids) == 1:
            product_id = next(iter(product_ids))
            resolved.append({"input": medicine, "kind": "product", "product_id": product_id, "ingredients": ingredient_index.get(product_id, [])})
            continue
        ingredient_rows = products[products["commercial_name_en"].str.casefold() == key]
        if len(ingredient_rows) == 0:
            unresolved.append({"input": medicine, "status": "PRODUCT_NOT_FOUND"})
        else:
            unresolved.append({"input": medicine, "status": "AMBIGUOUS_INGREDIENT_IDENTITY"})
    if unresolved:
        return {"status": unresolved[0]["status"], "resolved_medicines": resolved, "matches": [], "unresolved_pairs": unresolved, "coverage": {"queried_sources": sources or sorted(interactions["source_name"].unique())}}

    pairs = []
    for left, right in combinations(resolved, 2):
        for ingredient_a in left["ingredients"]:
            for ingredient_b in right["ingredients"]:
                if ingredient_a == ingredient_b:
                    continue
                pair = tuple(sorted((ingredient_a, ingredient_b)))
                if pair not in pairs:
                    pairs.append(pair)
    allowed = set(sources or interactions["source_name"].unique())
    evidence = interactions[interactions["source_name"].isin(allowed)].copy()
    evidence["pair_key"] = evidence.apply(lambda row: tuple(sorted((row["ingredient_a_id"], row["ingredient_b_id"]))), axis=1)
    matches = evidence[evidence["pair_key"].isin(pairs)].drop(columns=["pair_key"]).to_dict("records")
    return {
        "status": "DOCUMENTED_INTERACTION_FOUND" if matches else "NO_MATCH_FOUND_IN_QUERIED_SOURCES",
        "resolved_medicines": resolved,
        "matches": matches,
        "unresolved_pairs": [],
        "coverage": {"queried_sources": sorted(allowed), "candidate_pairs_checked": len(pairs), "evidence_rows_queried": len(evidence)},
    }