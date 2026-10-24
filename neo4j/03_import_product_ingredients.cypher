LOAD CSV WITH HEADERS FROM 'file:///product_ingredients.csv' AS row
WITH row WHERE row.graph_eligible = 'True' AND trim(row.product_id) <> '' AND trim(row.canonical_ingredient_id) <> ''
MATCH (p:DrugProduct {product_id: row.product_id})
MATCH (i:Ingredient {ingredient_id: row.canonical_ingredient_id})
MERGE (p)-[r:CONTAINS {token_position: toInteger(row.token_position), source_text: row.raw_token}]->(i)
SET r.strength = row.dose_candidate,
    r.resolution_status = row.resolution_status;