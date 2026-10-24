"""Stage 5 – Structural parsing of ``scientific_name``.

Responsibilities
----------------
* Detect which separator type(s) are present.
* Split combination drugs into individual ingredient tokens WITHOUT applying
  a global substitution when the separator's meaning is ambiguous.
* Extract embedded dosage strengths as CANDIDATE fields (not authoritative).
* Preserve every original token in full; nothing is deleted or renamed here.
* Produce a per-row ParseResult that records all flags raised.

Key design decisions and their rationale
-----------------------------------------
``/`` ambiguity
    The slash is used both as a *combination* separator (e.g.
    ``AMPICILLIN/SULBACTAM``) and as a *per-unit* notation (e.g.
    ``174.91 MG FERRIC PYROPHOSPHATE / 1 ML``).  The heuristic applied:
    if the substring immediately before or after ``/`` looks like a dose
    expression (digit + unit), treat it as per-unit notation and do NOT
    split on that ``/``.  All ``/`` splits are flagged
    ``SLASH_AMBIGUOUS`` so a human can confirm.

``=`` ambiguity
    ``=`` appears both as a synonym separator (``LEUCOVORIN CALCIUM=FOLINIC
    ACID``) and as an equative expression (``... = 40 MG TRADITIONAL
    LACTOFERRIN``).  No automated splitting is attempted; the whole token
    is kept and flagged ``EQUALS_AMBIGUOUS``.

``&`` inside parentheses
    ``VITAMIN E&C`` — the ``&`` joins sub-items inside a chemical name;
    it is NOT a combination separator here.  The heuristic: ``&`` is only
    treated as a combination separator when it sits outside any pair of
    parentheses and is surrounded by spaces (`` & ``).

Embedded-dose extraction
    A conservative regex pattern extracts numeric + unit strings (e.g.
    ``600 MG``, ``70%``, ``1000 IU``) as *candidate* dose fields.
    The ingredient name without the dose is stored as ``name_stripped``.
    Both values are kept; the caller must decide whether to trust them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Patterns ──────────────────────────────────────────────────────────────────

# Per-unit dose notation: a digit directly precedes or follows /
_SLASH_DOSE_RE = re.compile(
    r"""
    (?:                     # left side: number + optional unit
        \d[\d.,]*\s*(?:MG|MCG|G|ML|IU|%)\s*/
    )
    |
    (?:                     # right side: / followed by number + unit
        /\s*\d[\d.,]*\s*(?:MG|MCG|G|ML|IU|%)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Dose string embedded inside an ingredient token
_DOSE_EMBEDDED_RE = re.compile(
    r"""
    \b(\d[\d.,]*)           # numeric magnitude
    \s*                     # optional space
    (MG|MCG|G|IU|%|          # dose units
     ML|MMOL|MEQ|NANOMOL)
    (?=\b|$)                # '%' is non-word, so allow end-of-string
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Parenthetical content
_PAREN_RE = re.compile(r"\(([^)]*)\)")

# Spaced dash used as separator (must be surrounded by spaces)
_SPACED_DASH_RE = re.compile(r"\s+-\s+")

# Whole-word AND as separator
_AND_SEP_RE = re.compile(r"\bAND\b", re.IGNORECASE)

# Spaced ampersand as separator (outside parens – checked separately)
_AMP_SEP_RE = re.compile(r"\s+&\s+")


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class IngredientToken:
    """One ingredient parsed out of a ``scientific_name`` field.

    Attributes
    ----------
    raw_token:
        The exact string after splitting (whitespace-stripped, but otherwise
        unchanged from the source).
    name_stripped:
        ``raw_token`` with the detected dose expression removed.  If no
        dose was detected this equals ``raw_token``.  **Not authoritative** –
        the dose extraction is a heuristic.
    dose_candidate:
        The dose expression extracted from ``raw_token``, or ``None``.
        Labelled *candidate* because the extraction is heuristic; manual
        review is needed before treating it as structured data.
    parenthetical_content:
        Text found inside parentheses in the token, if any.
    position:
        1-based position of this token within the combination (1 for
        single-ingredient products).
    flags:
        List of parse-flag codes applied to this specific token.
    """

    raw_token: str
    name_stripped: str
    dose_candidate: Optional[str]
    parenthetical_content: Optional[str]
    position: int
    flags: List[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """Result of parsing one ``scientific_name`` value.

    Attributes
    ----------
    source_row_index:
        Maps back to the original CSV row.
    raw_scientific_name:
        The exact value from the source (or ``None``).
    tokens:
        List of ``IngredientToken`` objects extracted.
    separator_detected:
        The primary separator identified (``PLUS``, ``SLASH``, ``DASH``,
        ``AND``, ``AMP``, ``EQUALS``, ``NONE``).
    flags:
        Record-level parse flags (see constants below).
    """

    source_row_index: int
    raw_scientific_name: Optional[str]
    tokens: List[IngredientToken] = field(default_factory=list)
    separator_detected: str = "NONE"
    flags: List[str] = field(default_factory=list)


# ── Flag constants ────────────────────────────────────────────────────────────

FLAG_MISSING = "MISSING_SCI_NAME"
FLAG_TRUNCATED = "TRUNCATED_LIST"       # ends with '+'
FLAG_SLASH_AMBIGUOUS = "SLASH_AMBIGUOUS"
FLAG_EQUALS_AMBIGUOUS = "EQUALS_AMBIGUOUS"
FLAG_MIXED_SEPARATORS = "MIXED_SEPARATORS"
FLAG_EMBEDDED_DOSE = "EMBEDDED_DOSE"
FLAG_PARENTHETICAL = "HAS_PARENTHETICAL"
FLAG_PARSE_ERROR = "PARSE_ERROR"
FLAG_EMPTY_TOKEN = "EMPTY_TOKEN_PRODUCED"
FLAG_AND_SEPARATOR = "AND_SEPARATOR_USED"
FLAG_AMP_SEPARATOR = "AMP_SEPARATOR_USED"


# ── Public API ─────────────────────────────────────────────────────────────────


def parse_scientific_name(raw: Optional[str], source_row_index: int) -> ParseResult:
    """Parse one ``scientific_name`` value into structured tokens.

    Args:
        raw: The raw string from the ``scientific_name`` column, or ``None``.
        source_row_index: The 0-based row number from the source CSV.

    Returns:
        A ``ParseResult`` with all extracted tokens and flags.
    """
    result = ParseResult(
        source_row_index=source_row_index,
        raw_scientific_name=raw,
    )

    # ── Handle null / empty ──────────────────────────────────────────────────
    if raw is None or (isinstance(raw, float)):
        result.flags.append(FLAG_MISSING)
        return result

    s = str(raw).strip()
    if not s:
        result.flags.append(FLAG_MISSING)
        return result

    # ── Detect truncation ────────────────────────────────────────────────────
    if s.endswith("+"):
        result.flags.append(FLAG_TRUNCATED)
        s = s.rstrip("+").strip()

    # ── Detect equals sign ───────────────────────────────────────────────────
    if "=" in s:
        result.flags.append(FLAG_EQUALS_AMBIGUOUS)
        # Do NOT split on '='; treat the whole string as a single complex token
        result.separator_detected = "EQUALS"
        token = _parse_token(s, position=1)
        result.tokens.append(token)
        return result

    # ── Determine primary separator and split ────────────────────────────────
    has_plus = "+" in s
    has_slash = "/" in s and not _SLASH_DOSE_RE.search(s)
    has_slash_ambiguous = "/" in s
    has_dash = bool(_SPACED_DASH_RE.search(s))
    has_and = bool(_AND_SEP_RE.search(s))
    has_amp = _has_unparenthesised_amp(s)

    active_seps = sum([has_plus, has_slash, has_dash, has_and, has_amp])

    if active_seps > 1:
        result.flags.append(FLAG_MIXED_SEPARATORS)

    # Priority: + > / > spaced dash > AND > &
    if has_plus:
        result.separator_detected = "PLUS"
        raw_tokens = _split_on_plus(s)
    elif has_slash:
        result.separator_detected = "SLASH"
        result.flags.append(FLAG_SLASH_AMBIGUOUS)
        raw_tokens = [t.strip() for t in s.split("/") if t.strip()]
    elif has_dash:
        result.separator_detected = "DASH"
        raw_tokens = [t.strip() for t in _SPACED_DASH_RE.split(s) if t.strip()]
    elif has_and:
        result.separator_detected = "AND"
        result.flags.append(FLAG_AND_SEPARATOR)
        raw_tokens = [t.strip() for t in _AND_SEP_RE.split(s) if t.strip()]
    elif has_amp:
        result.separator_detected = "AMP"
        result.flags.append(FLAG_AMP_SEPARATOR)
        raw_tokens = [t.strip() for t in _AMP_SEP_RE.split(s) if t.strip()]
    else:
        # Single ingredient
        result.separator_detected = "NONE"
        raw_tokens = [s]

    # Flag ambiguous slash even when + took priority
    if has_slash_ambiguous:
        result.flags.append(FLAG_SLASH_AMBIGUOUS)

    # ── Parse each token ─────────────────────────────────────────────────────
    empty_tokens = 0
    for pos, tok in enumerate(raw_tokens, start=1):
        if not tok:
            empty_tokens += 1
            continue
        parsed_tok = _parse_token(tok, position=pos)
        result.tokens.append(parsed_tok)

    if empty_tokens:
        result.flags.append(FLAG_EMPTY_TOKEN)

    return result


def parse_dataframe(df: "pd.DataFrame") -> List[ParseResult]:  # noqa: F821
    """Parse every row's ``scientific_name`` column.

    Args:
        df: DataFrame containing ``source_row_index`` and ``scientific_name``.

    Returns:
        List of ``ParseResult`` objects, one per row, in the same order.
    """
    results: List[ParseResult] = []
    for _, row in df.iterrows():
        pr = parse_scientific_name(
            raw=row["scientific_name"] if "scientific_name" in row else None,
            source_row_index=int(row["source_row_index"]),
        )
        results.append(pr)
    return results


# ── Private helpers ───────────────────────────────────────────────────────────


def _split_on_plus(s: str) -> List[str]:
    """Split on '+', but not on '+' inside parentheses.

    Args:
        s: Input string.

    Returns:
        List of token strings.
    """
    tokens: List[str] = []
    depth = 0
    current: List[str] = []

    for ch in s:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "+" and depth == 0:
            tokens.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    tail = "".join(current).strip()
    if tail:
        tokens.append(tail)

    return [t for t in tokens if t]


def _has_unparenthesised_amp(s: str) -> bool:
    """Return True if '&' appears outside parentheses and is surrounded by spaces.

    Args:
        s: Input string.

    Returns:
        True if a spacing-surrounded ``&`` exists outside parentheses.
    """
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "&" and depth == 0:
            left = s[i - 1] if i > 0 else ""
            right = s[i + 1] if i < len(s) - 1 else ""
            if left == " " and right == " ":
                return True
    return False


def _parse_token(raw_tok: str, position: int) -> IngredientToken:
    """Parse a single ingredient token.

    Args:
        raw_tok: The raw ingredient string (already split from combination).
        position: 1-based position in the combination.

    Returns:
        An ``IngredientToken`` with extracted fields.
    """
    flags: List[str] = []

    # Extract parenthetical content
    paren_match = _PAREN_RE.search(raw_tok)
    parenthetical: Optional[str] = paren_match.group(1).strip() if paren_match else None
    if parenthetical is not None:
        flags.append(FLAG_PARENTHETICAL)

    # Extract embedded dose
    dose_match = _DOSE_EMBEDDED_RE.search(raw_tok)
    if dose_match:
        flags.append(FLAG_EMBEDDED_DOSE)
        dose_str = dose_match.group(0).strip()
        name_stripped = _DOSE_EMBEDDED_RE.sub("", raw_tok).strip(" .,")
        # Guard: if removing the dose leaves nothing, keep original
        if not name_stripped:
            name_stripped = raw_tok
    else:
        dose_str = None
        name_stripped = raw_tok

    return IngredientToken(
        raw_token=raw_tok,
        name_stripped=name_stripped,
        dose_candidate=dose_str,
        parenthetical_content=parenthetical,
        position=position,
        flags=flags,
    )
