"""Unit tests for the ingredient canonicalization module (Stage 5b).

Tests cover:
- Exact normalisation rules
- Documented synonym resolution
- Salt / chemical form handling
- Combination product components
- Ambiguous token handling (dose stripping, parenthetical, equals)
- Missing / null values
- Conflict detection
- Idempotency
"""

import math
import pytest
import pandas as pd
from pathlib import Path

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from drug_pipeline.canonicalizer import (
    STATUS_AUTO,
    STATUS_EXACT,
    STATUS_REVIEW,
    STATUS_UNRESOLVED,
    STATUS_REJECTED,
    CanonicalizationConflictError,
    _normalise_for_lookup,
    build_lookup,
    canonicalize_token_table,
    load_synonym_map,
    load_canonical_table,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def minimal_synonym_map() -> pd.DataFrame:
    return pd.DataFrame([
        {"raw_ingredient": "ACETAMINOPHEN",        "canonical_ingredient": "PARACETAMOL",  "mapping_type": "documented_synonym", "decision_status": "auto_approved",  "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "PARACETAMOL(ACETAMINOPHEN)", "canonical_ingredient": "PARACETAMOL", "mapping_type": "documented_synonym", "decision_status": "auto_approved",  "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "PARACETAMOL",          "canonical_ingredient": "PARACETAMOL",  "mapping_type": "exact_normalization", "decision_status": "auto_approved",  "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "VITAMIN C",             "canonical_ingredient": "ASCORBIC ACID","mapping_type": "documented_synonym", "decision_status": "auto_approved",  "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "VIT C",                 "canonical_ingredient": "ASCORBIC ACID","mapping_type": "documented_synonym", "decision_status": "auto_approved",  "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "CHOLECALCIFEROL(VITAMIN D3)", "canonical_ingredient": "CHOLECALCIFEROL", "mapping_type": "exact_normalization", "decision_status": "auto_approved", "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "VITAMIN D3",            "canonical_ingredient": "CHOLECALCIFEROL","mapping_type": "documented_synonym","decision_status": "auto_approved",  "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "VITAMIN B12",           "canonical_ingredient": "CYANOCOBALAMIN","mapping_type": "documented_synonym","decision_status": "needs_review",  "evidence_source": "WHO INN", "evidence_url": "", "notes": "ambiguous"},
        {"raw_ingredient": "IRON (FERROUS FUMARATE)","canonical_ingredient": "FERROUS FUMARATE","mapping_type": "salt_or_chemical_form","decision_status": "needs_review","evidence_source": "Ph.Eur.", "evidence_url": "", "notes": ""},
        {"raw_ingredient": "DEPRECATED DRUG",      "canonical_ingredient": "OLDNAME",      "mapping_type": "exact_normalization", "decision_status": "rejected",      "evidence_source": "", "evidence_url": "", "notes": ""},
    ])


@pytest.fixture
def minimal_canonical_table() -> pd.DataFrame:
    return pd.DataFrame([
        {"canonical_ingredient_id": "ING-0001", "canonical_name": "PARACETAMOL",    "preferred_display_name": "Paracetamol",    "ingredient_type": "active_ingredient", "review_status": "approved", "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"canonical_ingredient_id": "ING-0002", "canonical_name": "ASCORBIC ACID",  "preferred_display_name": "Ascorbic Acid",  "ingredient_type": "active_ingredient", "review_status": "approved", "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"canonical_ingredient_id": "ING-0003", "canonical_name": "CHOLECALCIFEROL","preferred_display_name": "Cholecalciferol","ingredient_type": "active_ingredient", "review_status": "approved", "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"canonical_ingredient_id": "ING-0007", "canonical_name": "CYANOCOBALAMIN", "preferred_display_name": "Cyanocobalamin", "ingredient_type": "active_ingredient", "review_status": "approved", "evidence_source": "WHO INN", "evidence_url": "", "notes": ""},
        {"canonical_ingredient_id": "ING-0021", "canonical_name": "FERROUS FUMARATE","preferred_display_name": "Ferrous Fumarate","ingredient_type": "mineral",         "review_status": "approved", "evidence_source": "Ph.Eur.", "evidence_url": "", "notes": ""},
    ])


@pytest.fixture
def minimal_lookup(minimal_synonym_map, minimal_canonical_table):
    return build_lookup(minimal_synonym_map, minimal_canonical_table)


@pytest.fixture
def token_df() -> pd.DataFrame:
    return pd.DataFrame([
        {"source_row_index": 0, "token_position": 1, "raw_token": "PARACETAMOL",            "name_stripped": "PARACETAMOL",         "separator_detected": "NONE"},
        {"source_row_index": 1, "token_position": 1, "raw_token": "ACETAMINOPHEN",           "name_stripped": "ACETAMINOPHEN",        "separator_detected": "NONE"},
        {"source_row_index": 2, "token_position": 1, "raw_token": "PARACETAMOL(ACETAMINOPHEN)", "name_stripped": "PARACETAMOL",      "separator_detected": "NONE"},
        {"source_row_index": 3, "token_position": 1, "raw_token": "VITAMIN C 500 MG",        "name_stripped": "VITAMIN C",           "separator_detected": "NONE"},
        {"source_row_index": 4, "token_position": 1, "raw_token": "VIT C 100MG",              "name_stripped": "VIT C",               "separator_detected": "NONE"},
        {"source_row_index": 5, "token_position": 1, "raw_token": "VITAMIN D3",               "name_stripped": "VITAMIN D3",          "separator_detected": "NONE"},
        {"source_row_index": 6, "token_position": 1, "raw_token": "CHOLECALCIFEROL(VITAMIN D3)", "name_stripped": "CHOLECALCIFEROL", "separator_detected": "NONE"},
        {"source_row_index": 7, "token_position": 1, "raw_token": "VITAMIN B12",              "name_stripped": "VITAMIN B12",         "separator_detected": "NONE"},
        {"source_row_index": 8, "token_position": 1, "raw_token": "IRON (FERROUS FUMARATE)",  "name_stripped": "IRON",                "separator_detected": "NONE"},
        {"source_row_index": 9, "token_position": 1, "raw_token": "UNKNOWN SUBSTANCE XYZ",   "name_stripped": "UNKNOWN SUBSTANCE XYZ","separator_detected": "NONE"},
        {"source_row_index":10, "token_position": 1, "raw_token": "DEPRECATED DRUG",         "name_stripped": "DEPRECATED DRUG",     "separator_detected": "NONE"},
        {"source_row_index":11, "token_position": 1, "raw_token": "",                         "name_stripped": "",                    "separator_detected": "NONE"},
    ])


# ─── _normalise_for_lookup ────────────────────────────────────────────────────

class TestNormalise:
    def test_uppercases(self):
        assert _normalise_for_lookup("ibuprofen") == "IBUPROFEN"

    def test_strips_dose(self):
        assert _normalise_for_lookup("VITAMIN C 500 MG") == "VITAMIN C"

    def test_strips_dose_no_space(self):
        assert _normalise_for_lookup("ZINC15MG") == "ZINC"

    def test_strips_parenthetical(self):
        assert _normalise_for_lookup("PARACETAMOL(ACETAMINOPHEN)") == "PARACETAMOL"

    def test_expands_vit(self):
        assert _normalise_for_lookup("VIT C") == "VITAMIN C"

    def test_expands_hcl(self):
        result = _normalise_for_lookup("PYRIDOXINE HCL")
        assert "HYDROCHLORIDE" in result

    def test_collapses_whitespace(self):
        assert _normalise_for_lookup("VITAMIN  C") == "VITAMIN C"

    def test_strips_iu_dose(self):
        assert _normalise_for_lookup("VITAMIN D3 1000 IU") == "VITAMIN D3"

    def test_strips_pct_dose(self):
        assert _normalise_for_lookup("UREA 10%") == "UREA"

    def test_empty_string(self):
        assert _normalise_for_lookup("") == ""

    def test_strips_leading_dose(self):
        # "900 MG VITAMIN C" → "VITAMIN C"
        result = _normalise_for_lookup("900 MG VITAMIN C")
        assert "VITAMIN C" in result


# ─── build_lookup ─────────────────────────────────────────────────────────────

class TestBuildLookup:
    def test_auto_approved_entries_present(self, minimal_lookup):
        assert "ACETAMINOPHEN" in minimal_lookup
        assert minimal_lookup.exact["ACETAMINOPHEN"][2] == STATUS_AUTO

    def test_needs_review_status_preserved(self, minimal_lookup):
        assert "VITAMIN B12" in minimal_lookup
        assert minimal_lookup.exact["VITAMIN B12"][2] == STATUS_REVIEW

    def test_rejected_status_preserved(self, minimal_lookup):
        assert "DEPRECATED DRUG" in minimal_lookup
        assert minimal_lookup.exact["DEPRECATED DRUG"][2] == STATUS_REJECTED

    def test_canonical_id_resolved(self, minimal_lookup):
        _, cid, _ = minimal_lookup.exact["PARACETAMOL"]
        assert cid == "ING-0001"

    def test_unknown_canonical_id_empty(self, minimal_lookup):
        _, cid, _ = minimal_lookup.exact["DEPRECATED DRUG"]
        assert cid == ""

    def test_conflict_raises(self, minimal_canonical_table):
        conflicting = pd.DataFrame([
            {"raw_ingredient": "IBUPROFEN", "canonical_ingredient": "IBUPROFEN",   "mapping_type": "exact_normalization", "decision_status": "auto_approved", "evidence_source": "", "evidence_url": "", "notes": ""},
            {"raw_ingredient": "IBUPROFEN", "canonical_ingredient": "PARACETAMOL", "mapping_type": "documented_synonym",  "decision_status": "auto_approved", "evidence_source": "", "evidence_url": "", "notes": ""},
        ])
        with pytest.raises(CanonicalizationConflictError):
            build_lookup(conflicting, minimal_canonical_table)


# ─── canonicalize_token_table ─────────────────────────────────────────────────

class TestCanonicalizeTokenTable:
    def test_exact_paracetamol_resolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "PARACETAMOL"].iloc[0]
        assert row["canonical_name"] == "PARACETAMOL"
        assert row["resolution_status"] in (STATUS_AUTO, STATUS_EXACT)

    def test_synonym_acetaminophen_resolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "ACETAMINOPHEN"].iloc[0]
        assert row["canonical_name"] == "PARACETAMOL"
        assert row["resolution_status"] == STATUS_AUTO

    def test_parenthetical_token_resolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "PARACETAMOL(ACETAMINOPHEN)"].iloc[0]
        assert row["canonical_name"] == "PARACETAMOL"

    def test_dose_embedded_token_resolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "VITAMIN C 500 MG"].iloc[0]
        assert row["canonical_name"] == "ASCORBIC ACID"
        assert row["resolution_status"] == STATUS_AUTO

    def test_abbreviated_vit_c_resolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "VIT C 100MG"].iloc[0]
        assert row["canonical_name"] == "ASCORBIC ACID"

    def test_common_name_vitamin_d3_resolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "VITAMIN D3"].iloc[0]
        assert row["canonical_name"] == "CHOLECALCIFEROL"

    def test_needs_review_preserved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "VITAMIN B12"].iloc[0]
        assert row["resolution_status"] == STATUS_REVIEW
        assert row["canonical_name"] == "CYANOCOBALAMIN"  # proposed but not auto-approved

    def test_salt_form_needs_review(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "IRON (FERROUS FUMARATE)"].iloc[0]
        assert row["resolution_status"] == STATUS_REVIEW

    def test_unknown_token_unresolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "UNKNOWN SUBSTANCE XYZ"].iloc[0]
        assert row["resolution_status"] == STATUS_UNRESOLVED
        assert row["canonical_name"] == ""

    def test_rejected_token_flagged(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == "DEPRECATED DRUG"].iloc[0]
        assert row["resolution_status"] == STATUS_REJECTED

    def test_empty_token_unresolved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        row = result[result["raw_token"] == ""].iloc[0]
        assert row["resolution_status"] == STATUS_UNRESOLVED

    def test_original_raw_token_preserved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        assert (result["raw_token"] == token_df["raw_token"]).all()

    def test_idempotent(self, token_df, minimal_lookup):
        r1 = canonicalize_token_table(token_df, minimal_lookup)
        r2 = canonicalize_token_table(token_df, minimal_lookup)
        pd.testing.assert_frame_equal(r1, r2)

    def test_no_hardcoded_row_count(self, token_df, minimal_lookup):
        subset = token_df.head(5)
        result = canonicalize_token_table(subset, minimal_lookup)
        assert len(result) == 5

    def test_result_has_required_columns(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        for col in ("normalised_lookup_key", "canonical_name", "canonical_ingredient_id", "resolution_status"):
            assert col in result.columns


# ─── Synonym map file loading ─────────────────────────────────────────────────

class TestLoadSynonymMap:
    def test_loads_real_file(self):
        path = Path(__file__).resolve().parents[2] / "config" / "ingredient_synonym_map.csv"
        df = load_synonym_map(path)
        assert len(df) > 0
        assert "raw_ingredient" in df.columns

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_synonym_map(tmp_path / "nonexistent.csv")

    def test_missing_column_raises(self, tmp_path):
        bad = tmp_path / "bad.csv"
        bad.write_text("col_a,col_b\n1,2\n")
        with pytest.raises(ValueError):
            load_synonym_map(bad)


# ─── Canonical table file loading ─────────────────────────────────────────────

class TestLoadCanonicalTable:
    def test_loads_real_file(self):
        path = Path(__file__).resolve().parents[2] / "config" / "canonical_ingredients.csv"
        df = load_canonical_table(path)
        assert len(df) > 0
        assert "canonical_ingredient_id" in df.columns

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_canonical_table(tmp_path / "nonexistent.csv")


# ─── Combination products ─────────────────────────────────────────────────────

class TestCombinationProducts:
    def test_each_token_resolved_independently(self, minimal_lookup):
        df = pd.DataFrame([
            {"source_row_index": 0, "token_position": 1, "raw_token": "PARACETAMOL",  "name_stripped": "PARACETAMOL",  "separator_detected": "PLUS"},
            {"source_row_index": 0, "token_position": 2, "raw_token": "ACETAMINOPHEN","name_stripped": "ACETAMINOPHEN","separator_detected": "PLUS"},
            {"source_row_index": 0, "token_position": 3, "raw_token": "VITAMIN C",    "name_stripped": "VITAMIN C",   "separator_detected": "PLUS"},
        ])
        result = canonicalize_token_table(df, minimal_lookup)
        assert result.iloc[0]["canonical_name"] == "PARACETAMOL"
        assert result.iloc[1]["canonical_name"] == "PARACETAMOL"
        assert result.iloc[2]["canonical_name"] == "ASCORBIC ACID"


# ─── Traceability ─────────────────────────────────────────────────────────────

class TestTraceability:
    def test_source_row_index_preserved(self, token_df, minimal_lookup):
        result = canonicalize_token_table(token_df, minimal_lookup)
        assert (result["source_row_index"].astype(str) == token_df["source_row_index"].astype(str)).all()
