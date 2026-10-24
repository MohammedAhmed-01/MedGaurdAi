# Pipeline Architecture — Egyptian Drug Knowledge Graph

> Generated: 2026-10-24

## Overview

```mermaid
flowchart TD
    A["Raw CSV\n(egyptian-drugs.csv)"] --> B["Stage 0: Load & Validate\n(loader.py)"]
    B --> C["Stage 1: Row-Level Cleaning\n(cleaner.py)"]
    C --> D["Stage 2: Manufacturer Parsing\n(cleaner.py)"]
    D --> E["Stage 3: Drug Class Canon.\n(cleaner.py)"]
    E --> F["Stage 4: Route Canon.\n(cleaner.py)"]
    F --> G["Stage 5: Scientific Name Parsing\n(ingredient_parser.py)"]
    G --> H["Stage 6: Token Inventory\n(inventory.py)"]
    H --> I["Stage 7: DQ Report & Output\n(reporter.py)"]
    
    H --> J["Stage 5b: Canonicalization\n(canonicalizer.py)"]
    J --> K["Stage 4*: Reference Validation"]
    K --> L["Stage 5*: Interaction Source Research"]
    L --> M["Stage 6*: Interaction KB Build"]
    
    I --> N["Stage 3*: Product Cleaning"]
    N --> O["Stage 7*: Interaction Detector"]
    M --> O
    
    N --> P["Stage 8-9: Neo4j Graph"]
    J --> P
    M --> P
    
    O --> Q["Stage 10: Testing & Validation"]
    P --> Q
    Q --> R["Stage 11: Final Deliverable"]
    
    style K fill:#ff9,stroke:#333
    style L fill:#ff9,stroke:#333
    style M fill:#ff9,stroke:#333
    style N fill:#ff9,stroke:#333
    style O fill:#ff9,stroke:#333
    style P fill:#ff9,stroke:#333
    style Q fill:#ff9,stroke:#333
    style R fill:#ff9,stroke:#333
```

> [!NOTE]
> Yellow nodes are NOT YET IMPLEMENTED. Stages marked with `*` use the user-request numbering, not the internal pipeline numbering.

## Execution Modes

### Mode 1: Full Pipeline (existing)
```bash
python run_pipeline.py --source data/egyptian-drugs.csv --output outputs/ --config config/
```
Runs Stages 0–7 (internal numbering), producing all outputs in `outputs/`.

### Mode 2: Canonicalization (standalone)
```python
from src.drug_pipeline.canonicalizer import run
run(
    token_table_path="outputs/ingredient_token_table.csv",
    synonym_map_path="config/ingredient_synonym_map.csv",
    canonical_table_path="config/canonical_ingredients.csv",
    output_dir="config/"
)
```

### Mode 3: Planned Stages (not yet implemented)
- Reference validation → `src/drug_pipeline/reference_validator.py`
- Interaction source retrieval → `src/drug_pipeline/interaction_sources.py`
- Interaction KB → `src/drug_pipeline/interaction_builder.py`
- Product cleaning → `src/drug_pipeline/product_cleaner.py`
- Interaction detector → `src/interaction_detector.py`
- Neo4j export → `src/drug_pipeline/neo4j_exporter.py`

## Data Flow

```mermaid
flowchart LR
    subgraph Input
        RAW["egyptian-drugs.csv\n25,070 rows × 7 cols"]
    end
    
    subgraph "Stage 0-7 Pipeline"
        LOAD["Load + source_row_index"] --> CLEAN["Cleaning + flags"]
        CLEAN --> PARSE["Parse scientific_name"]
        PARSE --> TOKENS["57,198 token occurrences\n8,499 unique tokens"]
        TOKENS --> DQ["DQ Report"]
    end
    
    subgraph "Canonicalization"
        SYNMAP["Synonym Map\n106 entries"]
        CANON["Canonical Table\n78 ingredients"]
        TOKENS --> CANONIZE["Two-tier lookup"]
        SYNMAP --> CANONIZE
        CANON --> CANONIZE
        CANONIZE --> RESOLVED["~12% resolved\n~82% unresolved"]
    end
    
    subgraph "Planned"
        RESOLVED --> VALIDATE["Reference Validation"]
        VALIDATE --> DDI["Interaction KB"]
        DDI --> GRAPH["Neo4j Graph"]
        DDI --> DETECT["Interaction Detector"]
    end
    
    RAW --> LOAD
```

## Technology Stack

- **Language**: Python 3.14+
- **Data Processing**: pandas
- **Graph Database**: Neo4j (planned)
- **Testing**: pytest
- **Dependencies**: pandas, colorama, pytest, coverage (from `requirements.txt`)

## Key Design Principles

1. **Immutability**: Source data is never modified. All transformations add new columns
2. **Traceability**: Every record has a `source_row_index` linking back to the raw CSV
3. **Conservative resolution**: Ambiguous cases are flagged, not automatically resolved
4. **Two-tier canonicalization**: Exact match first, normalized fallback only when unambiguous
5. **Configuration-driven**: Mapping files (CSV) drive canonicalization — no hardcoded rules
6. **Idempotent**: Re-running on the same inputs produces the same outputs

