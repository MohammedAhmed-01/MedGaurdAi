"""Egyptian Drug Normalization Pipeline.

Stages implemented:
    Stage 0 – Schema validation
    Stage 1 – Row-level cleaning (duplicates, status markers)
    Stage 2 – Manufacturer parsing
    Stage 3 – Drug-class canonicalization
    Stage 4 – Route canonicalization
    Stage 5 – scientific_name structural parsing
    Stage 6 – Ingredient-token inventory & review queue
    Stage 7 – Data-quality report
"""

__version__ = "0.1.0"
