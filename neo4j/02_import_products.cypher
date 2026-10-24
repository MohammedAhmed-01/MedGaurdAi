LOAD CSV WITH HEADERS FROM 'file:///medicine_products.csv' AS row
WITH row WHERE trim(row.product_id) <> ''
MERGE (p:DrugProduct {product_id: row.product_id})
SET p.commercial_name_en = row.commercial_name_en,
    p.commercial_name_ar = row.commercial_name_ar,
    p.manufacturer = row.manufacturer,
    p.drug_class = row.drug_class,
    p.route = row.route,
    p.price_egp = CASE WHEN trim(row.price_egp) = '' THEN null ELSE toFloat(row.price_egp) END,
    p.product_status = row.product_status,
    p.source_dataset = row.source_dataset,
    p.source_record_id = row.source_record_id,
    p.data_quality_status = row.data_quality_status;