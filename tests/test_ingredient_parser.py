"""Unit tests for the ingredient parser (Stage 5).

Each test covers one specific parsing behaviour.  Tests never hit the
real CSV; all inputs are hand-crafted strings.
"""

import pytest

from src.drug_pipeline.ingredient_parser import (
    FLAG_AND_SEPARATOR,
    FLAG_AMP_SEPARATOR,
    FLAG_EMBEDDED_DOSE,
    FLAG_EQUALS_AMBIGUOUS,
    FLAG_MISSING,
    FLAG_PARENTHETICAL,
    FLAG_SLASH_AMBIGUOUS,
    FLAG_TRUNCATED,
    FLAG_MIXED_SEPARATORS,
    parse_scientific_name,
    _split_on_plus,
    _has_unparenthesised_amp,
    _parse_token,
)


# ─────────────────────────────────────────────────────────────────────────────
# Null / empty input
# ─────────────────────────────────────────────────────────────────────────────


class TestNullAndEmpty:
    def test_none_input(self):
        result = parse_scientific_name(None, source_row_index=0)
        assert FLAG_MISSING in result.flags
        assert result.tokens == []

    def test_float_nan(self):
        import math
        result = parse_scientific_name(float("nan"), source_row_index=1)
        assert FLAG_MISSING in result.flags

    def test_empty_string(self):
        result = parse_scientific_name("", source_row_index=2)
        assert FLAG_MISSING in result.flags
        assert result.tokens == []

    def test_whitespace_only(self):
        result = parse_scientific_name("   ", source_row_index=3)
        assert FLAG_MISSING in result.flags


# ─────────────────────────────────────────────────────────────────────────────
# Single-ingredient
# ─────────────────────────────────────────────────────────────────────────────


class TestSingleIngredient:
    def test_simple(self):
        result = parse_scientific_name("IBUPROFEN", source_row_index=10)
        assert len(result.tokens) == 1
        assert result.tokens[0].raw_token == "IBUPROFEN"
        assert result.separator_detected == "NONE"
        assert result.flags == []

    def test_preserves_original(self):
        raw = "AMOXICILLIN"
        result = parse_scientific_name(raw, source_row_index=11)
        assert result.raw_scientific_name == raw
        assert result.tokens[0].raw_token == raw


# ─────────────────────────────────────────────────────────────────────────────
# Plus-separator (the dominant case)
# ─────────────────────────────────────────────────────────────────────────────


class TestPlusSeparator:
    def test_two_ingredients(self):
        result = parse_scientific_name("AMOXICILLIN+CLAVULANIC ACID", 20)
        assert result.separator_detected == "PLUS"
        assert len(result.tokens) == 2
        tokens = [t.raw_token for t in result.tokens]
        assert "AMOXICILLIN" in tokens
        assert "CLAVULANIC ACID" in tokens

    def test_three_ingredients(self):
        result = parse_scientific_name(
            "CHLORPHENIRAMINE+PARACETAMOL+PSEUDOEPHEDRINE", 21
        )
        assert len(result.tokens) == 3

    def test_plus_inside_parens_not_split(self):
        """A '+' inside parentheses must not be treated as a separator."""
        raw = "VITAMINS(A+D+E)+ZINC"
        result = parse_scientific_name(raw, 22)
        assert result.separator_detected == "PLUS"
        # Should produce 2 tokens: VITAMINS(A+D+E) and ZINC
        assert len(result.tokens) == 2
        assert result.tokens[0].raw_token == "VITAMINS(A+D+E)"
        assert result.tokens[1].raw_token == "ZINC"

    def test_position_numbering(self):
        result = parse_scientific_name("A+B+C", 23)
        positions = [t.position for t in result.tokens]
        assert positions == [1, 2, 3]

    def test_whitespace_stripped_from_tokens(self):
        result = parse_scientific_name("  SODIUM  +  POTASSIUM  ", 24)
        assert result.tokens[0].raw_token == "SODIUM"
        assert result.tokens[1].raw_token == "POTASSIUM"


# ─────────────────────────────────────────────────────────────────────────────
# Truncated lists
# ─────────────────────────────────────────────────────────────────────────────


class TestTruncatedList:
    def test_trailing_plus_flagged(self):
        result = parse_scientific_name("VITAMIN C+ZINC+", 30)
        assert FLAG_TRUNCATED in result.flags

    def test_truncated_tokens_still_extracted(self):
        result = parse_scientific_name("VITAMIN C+ZINC+", 31)
        assert len(result.tokens) == 2

    def test_non_truncated_not_flagged(self):
        result = parse_scientific_name("VITAMIN C+ZINC", 32)
        assert FLAG_TRUNCATED not in result.flags


# ─────────────────────────────────────────────────────────────────────────────
# Equals ambiguity
# ─────────────────────────────────────────────────────────────────────────────


class TestEqualsAmbiguity:
    def test_equals_flagged(self):
        result = parse_scientific_name(
            "LEUCOVORIN CALCIUM=FOLINIC ACID=CALCIUM FOLINATE", 40
        )
        assert FLAG_EQUALS_AMBIGUOUS in result.flags

    def test_equals_not_split(self):
        """The full string must be kept as a single token, not split on '='."""
        result = parse_scientific_name("LEUCOVORIN CALCIUM=FOLINIC ACID", 41)
        assert len(result.tokens) == 1
        assert result.tokens[0].raw_token == "LEUCOVORIN CALCIUM=FOLINIC ACID"


# ─────────────────────────────────────────────────────────────────────────────
# Slash ambiguity
# ─────────────────────────────────────────────────────────────────────────────


class TestSlashAmbiguity:
    def test_combination_slash_flagged(self):
        result = parse_scientific_name("VALSARTAN/SACUBITRIL", 50)
        assert FLAG_SLASH_AMBIGUOUS in result.flags

    def test_combination_slash_splits(self):
        result = parse_scientific_name("VALSARTAN/SACUBITRIL", 51)
        # When used as combination separator, should produce 2 tokens
        assert len(result.tokens) == 2

    def test_dose_per_unit_slash_not_split(self):
        """'/ 1 ML' is per-unit notation, not a combination separator."""
        raw = "174.91 MG LIPOSOMAL FERRIC PYROPHOSPHATE / 1 ML"
        result = parse_scientific_name(raw, 52)
        # Should NOT produce 2 tokens by splitting on the dose '/ 1 ML'
        # The whole string stays as one unit (separator_detected != SLASH without dose)
        # It may end up NONE or EQUALS_AMBIGUOUS; key check: not split into dose portion
        raw_tokens = [t.raw_token for t in result.tokens]
        # The word 'ML' should not be a standalone token
        assert not any(t.strip() in ("1 ML", "ML", "1") for t in raw_tokens)


# ─────────────────────────────────────────────────────────────────────────────
# AND / & separators
# ─────────────────────────────────────────────────────────────────────────────


class TestAndAmpSeparators:
    def test_and_separator(self):
        result = parse_scientific_name("GLUCOSAMINE AND CHONDROITIN", 60)
        assert FLAG_AND_SEPARATOR in result.flags
        assert len(result.tokens) == 2

    def test_amp_outside_parens(self):
        result = parse_scientific_name("VITAMIN E & VITAMIN C", 61)
        assert FLAG_AMP_SEPARATOR in result.flags
        assert len(result.tokens) == 2

    def test_amp_inside_name_not_split(self):
        """'E&C' (no spaces) should NOT be treated as a combination separator."""
        result = parse_scientific_name("VITAMIN E&C+ZINC", 62)
        # Primary separator is '+'; the E&C stays as one token
        raw_tokens = [t.raw_token for t in result.tokens]
        assert "VITAMIN E&C" in raw_tokens
        assert "ZINC" in raw_tokens


# ─────────────────────────────────────────────────────────────────────────────
# Spaced-dash separator
# ─────────────────────────────────────────────────────────────────────────────


class TestSpacedDashSeparator:
    def test_spaced_dash_splits(self):
        result = parse_scientific_name("IRON - FOLIC ACID - ZINC", 70)
        assert result.separator_detected == "DASH"
        assert len(result.tokens) == 3

    def test_hyphen_in_name_not_split(self):
        """An intra-word hyphen like 'N-ACETYL' must not be split."""
        result = parse_scientific_name("N-ACETYL CYSTEINE+GLUTATHIONE", 71)
        tokens = [t.raw_token for t in result.tokens]
        assert "N-ACETYL CYSTEINE" in tokens


# ─────────────────────────────────────────────────────────────────────────────
# Parenthetical content
# ─────────────────────────────────────────────────────────────────────────────


class TestParentheticalContent:
    def test_synonym_detected(self):
        result = parse_scientific_name("PARACETAMOL(ACETAMINOPHEN)", 80)
        tok = result.tokens[0]
        assert FLAG_PARENTHETICAL in tok.flags
        assert tok.parenthetical_content == "ACETAMINOPHEN"

    def test_raw_token_preserved(self):
        raw = "PARACETAMOL(ACETAMINOPHEN)"
        result = parse_scientific_name(raw, 81)
        assert result.tokens[0].raw_token == raw

    def test_multi_synonym(self):
        result = parse_scientific_name(
            "MESALAZINE(MESALAMINE)(5-ASA)", 82
        )
        tok = result.tokens[0]
        assert FLAG_PARENTHETICAL in tok.flags
        # raw_token must be preserved fully
        assert tok.raw_token == "MESALAZINE(MESALAMINE)(5-ASA)"


# ─────────────────────────────────────────────────────────────────────────────
# Embedded dose extraction
# ─────────────────────────────────────────────────────────────────────────────


class TestEmbeddedDose:
    def test_mg_dose_extracted(self):
        tok = _parse_token("METFORMIN 500 MG", position=1)
        assert FLAG_EMBEDDED_DOSE in tok.flags
        assert tok.dose_candidate is not None
        assert "500" in tok.dose_candidate

    def test_mcg_dose_extracted(self):
        tok = _parse_token("FOLIC ACID 400 MCG", position=1)
        assert FLAG_EMBEDDED_DOSE in tok.flags

    def test_percent_dose_extracted(self):
        tok = _parse_token("UREA 10%", position=1)
        assert FLAG_EMBEDDED_DOSE in tok.flags

    def test_raw_token_unchanged_when_dose_present(self):
        raw = "ZINC 15 MG"
        tok = _parse_token(raw, position=1)
        assert tok.raw_token == raw

    def test_name_stripped_removes_dose(self):
        tok = _parse_token("METFORMIN 500 MG", position=1)
        assert "METFORMIN" in tok.name_stripped
        assert "500" not in tok.name_stripped

    def test_no_dose_gives_none_candidate(self):
        tok = _parse_token("AMOXICILLIN", position=1)
        assert tok.dose_candidate is None
        assert FLAG_EMBEDDED_DOSE not in tok.flags

    def test_name_not_emptied_if_only_dose(self):
        """If stripping the dose would empty the name, keep the raw token."""
        tok = _parse_token("1000 MG", position=1)
        assert tok.name_stripped  # must not be empty


# ─────────────────────────────────────────────────────────────────────────────
# Source-row traceability
# ─────────────────────────────────────────────────────────────────────────────


class TestTraceability:
    def test_source_row_index_preserved(self):
        for idx in [0, 999, 25069]:
            result = parse_scientific_name("IBUPROFEN", idx)
            assert result.source_row_index == idx

    def test_raw_value_preserved_in_result(self):
        raw = "AMOXICILLIN+CLAVULANIC ACID"
        result = parse_scientific_name(raw, 100)
        assert result.raw_scientific_name == raw


# ─────────────────────────────────────────────────────────────────────────────
# Mixed separators
# ─────────────────────────────────────────────────────────────────────────────


class TestMixedSeparators:
    def test_mixed_flagged(self):
        result = parse_scientific_name(
            "PEPPERMINT+CAMPHOR & MENTHOL", 90
        )
        assert FLAG_MIXED_SEPARATORS in result.flags

    def test_plus_takes_priority_over_amp(self):
        result = parse_scientific_name(
            "A+B & C+D", 91
        )
        assert result.separator_detected == "PLUS"


# ─────────────────────────────────────────────────────────────────────────────
# Internal helper tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHelpers:
    def test_split_on_plus_basic(self):
        assert _split_on_plus("A+B+C") == ["A", "B", "C"]

    def test_split_on_plus_preserves_parens(self):
        assert _split_on_plus("A(X+Y)+B") == ["A(X+Y)", "B"]

    def test_split_on_plus_nested_parens(self):
        assert _split_on_plus("A((X+Y))+B") == ["A((X+Y))", "B"]

    def test_has_unparenthesised_amp_true(self):
        assert _has_unparenthesised_amp("A & B") is True

    def test_has_unparenthesised_amp_false_no_spaces(self):
        assert _has_unparenthesised_amp("E&C") is False

    def test_has_unparenthesised_amp_false_inside_parens(self):
        assert _has_unparenthesised_amp("(E & C)") is False
