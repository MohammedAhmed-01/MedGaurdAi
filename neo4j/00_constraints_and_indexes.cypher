CREATE CONSTRAINT drug_product_id IF NOT EXISTS FOR (p:DrugProduct) REQUIRE p.product_id IS UNIQUE;
CREATE CONSTRAINT ingredient_id IF NOT EXISTS FOR (i:Ingredient) REQUIRE i.ingredient_id IS UNIQUE;
CREATE CONSTRAINT evidence_source_id IF NOT EXISTS FOR (s:EvidenceSource) REQUIRE s.source_id IS UNIQUE;
CREATE INDEX drug_product_name_en IF NOT EXISTS FOR (p:DrugProduct) ON (p.commercial_name_en);
CREATE INDEX drug_product_name_ar IF NOT EXISTS FOR (p:DrugProduct) ON (p.commercial_name_ar);
CREATE INDEX ingredient_name IF NOT EXISTS FOR (i:Ingredient) ON (i.canonical_name);