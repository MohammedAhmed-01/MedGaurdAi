import pandas as pd

from src.interaction_detector import check_interactions


def _fixtures(tmp_path):
    products = pd.DataFrame([
        {"product_id": "P1", "commercial_name_en": "ALPHA", "commercial_name_ar": "ألفا"},
        {"product_id": "P2", "commercial_name_en": "BETA", "commercial_name_ar": "بيتا"},
    ])
    aliases = pd.DataFrame([
        {"product_id": "P1", "alias_type": "ENGLISH", "alias_value": "ALPHA"},
        {"product_id": "P2", "alias_type": "ENGLISH", "alias_value": "BETA"},
    ])
    product_ingredients = pd.DataFrame([
        {"product_id": "P1", "canonical_ingredient_id": "I1", "graph_eligible": True},
        {"product_id": "P2", "canonical_ingredient_id": "I2", "graph_eligible": True},
    ])
    interaction = pd.DataFrame([{
        "interaction_id": "X1", "ingredient_a_id": "I1", "ingredient_b_id": "I2",
        "source_name": "TEST_SOURCE", "source_url": "https://example.invalid/evidence",
    }])
    paths = []
    for name, frame in (("products", products), ("aliases", aliases), ("ingredients", product_ingredients), ("interactions", interaction)):
        path = tmp_path / f"{name}.csv"
        frame.to_csv(path, index=False)
        paths.append(path)
    return paths


def test_missing_evidence_is_not_safe(tmp_path):
    result = check_interactions(["ALPHA", "BETA"], interactions_path=tmp_path / "missing.csv")
    assert result["status"] == "SOURCE_QUERY_FAILED"


def test_documented_pair_is_returned(tmp_path):
    products, aliases, ingredients, interactions = _fixtures(tmp_path)
    result = check_interactions(["ALPHA", "BETA"], products_path=products, aliases_path=aliases, ingredients_path=ingredients, interactions_path=interactions)
    assert result["status"] == "DOCUMENTED_INTERACTION_FOUND"
    assert result["matches"][0]["interaction_id"] == "X1"


def test_arabic_alias_resolves(tmp_path):
    products, aliases, ingredients, interactions = _fixtures(tmp_path)
    arabic_aliases = pd.read_csv(aliases)
    arabic_aliases.loc[len(arabic_aliases)] = ["P1", "ARABIC", "ألفا"]
    arabic_aliases.to_csv(aliases, index=False)
    result = check_interactions(["ألفا", "BETA"], products_path=products, aliases_path=aliases, ingredients_path=ingredients, interactions_path=interactions)
    assert result["status"] == "DOCUMENTED_INTERACTION_FOUND"


def test_unknown_product_is_explicit(tmp_path):
    products, aliases, ingredients, interactions = _fixtures(tmp_path)
    result = check_interactions(["UNKNOWN", "BETA"], products_path=products, aliases_path=aliases, ingredients_path=ingredients, interactions_path=interactions)
    assert result["status"] == "PRODUCT_NOT_FOUND"