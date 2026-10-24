// Stable IDs must be unique by constraint.
MATCH (p:DrugProduct) RETURN count(p) AS product_count;
MATCH (i:Ingredient) RETURN count(i) AS ingredient_count;
MATCH ()-[r:CONTAINS]->() RETURN count(r) AS contains_count;
MATCH ()-[r:INTERACTS_WITH]->() WHERE r.source_url IS NULL OR trim(r.source_url) = '' RETURN count(r) AS interactions_without_source;
MATCH (p:DrugProduct) WHERE NOT (p)-[:CONTAINS]->() RETURN p.product_id, p.commercial_name_en LIMIT 100;
MATCH (p:DrugProduct)-[:CONTAINS]->(i:Ingredient) RETURN p.product_id, p.commercial_name_en, i.ingredient_id, i.canonical_name LIMIT 20;