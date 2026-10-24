# Interaction Source Assessment

This is a planning and governance artifact. No interaction source was queried, downloaded, or inspected in the current run, and no interaction records are asserted.

| Source | Intended role | Current status | Main constraint |
|---|---|---|---|
| DDInter 2.0 | Candidate structured interaction dataset | NOT_VERIFIED | Dataset availability, schema, identifiers, licensing, and redistribution terms require inspection before use. |
| DailyMed | Official US label evidence | NOT_VERIFIED | Label lookup and permitted reuse must be checked for each evidence record. |
| FDA drug labeling resources | Regulatory labeling evidence | NOT_VERIFIED | Evidence must come from an inspected official label or document, not a general URL. |
| RxNorm/RxNav | Drug terminology and identity mapping | NOT_VERIFIED | Primarily an identity service; it is not treated as an interaction source by default. |
| DrugBank | Potential licensed interaction reference | NOT_VERIFIED | License and redistribution restrictions must be resolved before any use. |

## Acceptance gate

A source may move from `NOT_VERIFIED` to `APPROVED_FOR_INGESTION` only after its actual access method, schema, identifier semantics, evidence fields, licensing, and retrieval date have been inspected and recorded in `data/reference/interaction_source_registry.csv`. Until then, the interaction knowledge base remains empty by design.