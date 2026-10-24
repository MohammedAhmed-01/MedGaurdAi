# Neo4j Import Package

Assumptions: Neo4j 5.x and UTF-8 CSV files in the server import directory. No plugins are required. These scripts were generated but not executed against a Neo4j instance.

Prepare these files under the import directory: `canonical_ingredients.csv`, `medicine_products.csv`, `product_ingredients.csv`, and `interaction_source_registry.csv`. The canonical table comes from `config/`; the product files come from `data/clean/`; copy the registry from `data/reference/`.

Run scripts in order from `00` through `07`. The product-ingredient script imports only rows with `graph_eligible = True`; the interaction script imports only `ACCEPTED` evidence rows. The current interaction file has headers only, so it creates no interaction edges.

Before import, validate headers, UTF-8 encoding, and rejected rows. To rerun safely, the constraints and `MERGE` statements make node and relationship loading idempotent for unchanged stable IDs. For a clean replacement, use a disposable database or delete only this graph's labels after backing up data. Run validation queries after every import and retain rejected-row logs.