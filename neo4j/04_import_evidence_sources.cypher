LOAD CSV WITH HEADERS FROM 'file:///interaction_source_registry.csv' AS row
WITH row WHERE trim(row.source_id) <> '' AND row.verification_status = 'APPROVED_FOR_INGESTION'
MERGE (s:EvidenceSource {source_id: row.source_id})
SET s.source_name = row.source_name,
    s.source_url = row.official_url,
    s.source_type = row.access_method,
    s.license = row.license_or_redistribution,
    s.retrieved_at = row.last_inspected_at;