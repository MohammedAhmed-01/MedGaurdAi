LOAD CSV WITH HEADERS FROM 'file:///canonical_ingredients.csv' AS row
WITH row WHERE trim(row.canonical_ingredient_id) <> ''
MERGE (i:Ingredient {ingredient_id: row.canonical_ingredient_id})
SET i.canonical_name = row.canonical_name,
    i.display_name = row.preferred_display_name,
    i.ingredient_type = row.ingredient_type,
    i.identity_status = row.review_status,
    i.evidence_source = row.evidence_source,
    i.evidence_url = row.evidence_url;