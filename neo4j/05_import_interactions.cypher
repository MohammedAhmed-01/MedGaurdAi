LOAD CSV WITH HEADERS FROM 'file:///ingredient_interactions.csv' AS row
WITH row WHERE trim(row.interaction_id) <> '' AND row.review_status = 'ACCEPTED'
MATCH (a:Ingredient {ingredient_id: row.ingredient_a_id})
MATCH (b:Ingredient {ingredient_id: row.ingredient_b_id})
MERGE (a)-[r:INTERACTS_WITH {interaction_id: row.interaction_id}]->(b)
SET r.interaction_type = row.interaction_type,
    r.severity_source_value = row.severity_source_value,
    r.severity_normalized = row.severity_normalized,
    r.mechanism = row.mechanism,
    r.clinical_effect = row.clinical_effect,
    r.clinical_recommendation = row.clinical_recommendation,
    r.evidence_level = row.evidence_level,
    r.source_name = row.source_name,
    r.source_record_id = row.source_record_id,
    r.source_url = row.source_url,
    r.retrieved_at = row.retrieved_at;