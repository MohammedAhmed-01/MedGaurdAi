# Neo4j Graph Schema

The import package uses stable source-derived product IDs and canonical ingredient IDs. Unresolved or review mappings are not imported as product-ingredient edges.

Nodes: `DrugProduct`, `Ingredient`, `EvidenceSource`.

Relationships: `DrugProduct-[:CONTAINS]->Ingredient`, `Ingredient-[:INTERACTS_WITH]->Ingredient`, and `InteractionEvidence-[:SUPPORTED_BY]->EvidenceSource` may be extended when accepted evidence records exist. The current interaction table is empty, so no interaction edges are created.

CSV files are UTF-8 with headers. Place import files in Neo4j's configured `import` directory and use the documented `file:///` names. Scripts have not been executed against a Neo4j instance in this session.