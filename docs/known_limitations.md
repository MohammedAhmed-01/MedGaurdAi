# Known Limitations

- The source dataset has no registration number, barcode, or authoritative current-market status field.
- Ingredient canonicalization remains incomplete: 46,824 of 57,198 token occurrences were unresolved in the validated rerun.
- Only 6,476 product-ingredient links are currently graph-eligible; this is not complete product coverage.
- Existing evidence URLs in the curation files have not been queried in this run.
- No approved interaction source was queried or downloaded, so the interaction evidence tables contain zero confirmed records.
- An empty interaction lookup means no match in the queried local evidence, not that a combination is safe.
- Patient-specific clinical risk can depend on dose, formulation, route, age, comorbidities, organ function, and other medicines.
- Neo4j scripts and import execution remain outstanding and must be gated on reviewed identity and interaction evidence.