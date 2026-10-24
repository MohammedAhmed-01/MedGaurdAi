// Replace product IDs with selected products. An empty result means no imported edge, not safety.
MATCH (p1:DrugProduct {product_id: $product_id_a})-[:CONTAINS]->(i1:Ingredient)
MATCH (p2:DrugProduct {product_id: $product_id_b})-[:CONTAINS]->(i2:Ingredient)
MATCH (i1)-[r:INTERACTS_WITH]-(i2)
RETURN p1.product_id, p2.product_id, i1.canonical_name, i2.canonical_name, r;