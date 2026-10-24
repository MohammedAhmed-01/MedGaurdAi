# Product Cleaning Report

This package preserves every source product and token relationship. It does not merge products or infer missing ingredients.

- Source products: 25,070
- Product aliases: 50,140
- Product-ingredient token rows: 57,198
- Graph-eligible token rows: 6,476
- Products in review queue: 24,024

## Stable Identity

`product_id` is derived from the immutable source row index as `EGP-00001` style identifiers. It is a source-record identifier, not an invented regulatory or registration number.

## Graph Boundary

All token rows remain in `data/clean/product_ingredients.csv`. The `graph_eligible` flag is false unless the canonical mapping is an accepted mapping or exact pass-through and the canonical ingredient is marked approved. Unresolved and review rows are never silently promoted.
