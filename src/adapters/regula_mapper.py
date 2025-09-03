# src/adapters/regula_mapper.py
from __future__ import annotations
from typing import Any, Dict, Iterable, List, Tuple, Optional
import re

# ---- Universal field aliases (human names seen in Regula) ----
FIELD_KEYS = {
    "number": ["document number", "number", "passport number", "doc number"],
    "country": [ "nationality code", "country code"],
    "name": ["given names", "given name(s)", "first name", "first names", "name"],
    "surname": ["surname", "last name", "secondary id"],
    "middle name": ["middle name", "middle names"],
    "gender": ["gender", "sex"],
    "place of birth": ["place of birth", "birth place"],
    "birth date": ["date of birth", "birth date"],
    "issue date": ["date of issue", "issue date"],
    "expiry date": ["date of expiry", "expiry date", "expiration date"],
    "mother name": ["mother name", "mother's name"],
    "father name": ["father name", "father's name", "guardian"],
    "spouse name": ["spouse name", "spouse"],
    "place of issue": ["issuing authority", "issuing state", "place of issue", "authority", "issuing office"],
    "country of issue": ["issuing state code", "issuing country", "issuing state name"],
}

# For selection logic: which source to prefer when both exist.
PREFER_SOURCE: Dict[str, str] = {
    # MRZ is typically more canonical for these:
    "number": "MRZ",
    "birth date": "MRZ",
    "expiry date": "MRZ",
    # MRZ does not contain issue date; prefer VISUAL there:
    "issue date": "VISUAL",
    # everything else defaults to VISUAL unless only MRZ exists.
}

MRZ_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")

# -------------- helpers --------------

def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", (str(s or "")).strip())

def _lower(s: str) -> str:
    return _norm(s).lower()

def _best_mrz_lines(s: str) -> Tuple[str, str]:
    """
    Split the 'MRZ Strings' value into up to two 44-char-ish lines.
    Accept only strings containing '<' and most chars from MRZ alphabet.
    """
    lines = re.split(r"[\r\n]+", s or "")
    cands = []
    for line in lines:
        t = _norm(line)
        if len(t) >= 30 and "<" in t and set(t) <= MRZ_ALLOWED:
            cands.append(t)
    # keep two best by length
    cands.sort(key=len, reverse=True)
    l1 = cands[0] if len(cands) > 0 else ""
    l2 = cands[1] if len(cands) > 1 else ""
    return l1, l2

def _dig(obj: Dict[str, Any]) -> Dict[str, Any]:
    """Return the dict under low_lvl_response if present; else obj."""
    return obj.get("low_lvl_response") or obj

# -------------- core extraction --------------

def _iter_field_entries(raw: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """
    Yield every Text.fieldList entry in ContainerList.List[*].
    Compatible with 8.x low-level response.
    """
    data = _dig(raw)
    cl = (data or {}).get("ContainerList") or {}
    for item in (cl.get("List") or []):
        text = item.get("Text") or {}
        for f in (text.get("fieldList") or []):
            yield f

def _build_field_index(raw: Dict[str, Any]) -> Dict[str, Dict[str, List[Tuple[str, float]]]]:
    """
    Build an index: name_lower -> { 'MRZ': [(value, prob), ...], 'VISUAL': [(value, prob), ...] }
    """
    idx: Dict[str, Dict[str, List[Tuple[str, float]]]] = {}
    for f in _iter_field_entries(raw):
        name = _lower(f.get("fieldName") or f.get("name"))
        vlist = f.get("valueList") or []
        if not name:
            continue
        # Initialize buckets
        rec = idx.setdefault(name, {"MRZ": [], "VISUAL": []})
        for v in vlist:
            src = str(v.get("source") or "").upper()
            if src not in ("MRZ", "VISUAL"):
                continue
            val = _norm(v.get("value") or v.get("originalValue"))
            # Regula returns probability as 0-100, normalize to 0.0-1.0 scale
            prob = float(v.get("probability") or 0) / 100.0
            if val:
                rec[src].append((val, prob))

        # If no valueList (rare), fall back to flat 'value'
        if not rec["MRZ"] and not rec["VISUAL"]:
            flat_val = _norm(f.get("value"))
            if flat_val:
                # Unknown source; treat as VISUAL by default
                # Normalize probability from 0-100 to 0.0-1.0 scale
                rec["VISUAL"].append((flat_val, float(f.get("probability") or 0) / 100.0))
    return idx

def _choose_value(
    idx: Dict[str, Dict[str, List[Tuple[str, float]]]],
    aliases: List[str],
    prefer: Optional[str] = None
) -> Tuple[str, str, float]:
    """
    Choose a value for the field:
    - search aliases in the index,
    - prefer requested source (MRZ/VISUAL) if available,
    - otherwise take the source with the highest-probability candidate.
    Returns (value, chosen_source, chosen_prob)
    """
    names = [_lower(a) for a in aliases]
    # Find the first present name
    key = next((n for n in names if n in idx), None)
    if key is None:
        # fuzzy contains
        for k in idx.keys():
            if any(n in k for n in names):
                key = k
                break
    if key is None:
        return "", "", 0.0

    rec = idx[key]
    # Prefer requested source if present
    if prefer in ("MRZ", "VISUAL") and rec.get(prefer):
        cand = max(rec[prefer], key=lambda t: t[1] if isinstance(t[1], (int, float)) else -1)
        return cand[0], prefer, float(cand[1] or 0)

    # Else, pick the source with best probability
    best_src, best_val, best_prob = "", "", -1.0
    for src in ("VISUAL", "MRZ"):  # VISUAL slightly preferred when probs tie
        for val, prob in rec.get(src, []):
            pr = float(prob or 0)
            if pr > best_prob:
                best_src, best_val, best_prob = src, val, pr
    if best_src:
        return best_val, best_src, best_prob
    return "", "", 0.0

# -------------- public API --------------

def regula_to_universal(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert Regula low-level response to your universal dict.
    - Picks a single value per target field (according to source preference rules)
    - Adds MRZ lines
    - Includes Regula probability scores for each field
    """
    idx = _build_field_index(raw)

    probabilities: Dict[str, float] = {}

    def pick(label: str) -> str:
        prefer = PREFER_SOURCE.get(label)  # 'MRZ', 'VISUAL', or None
        val, src, prob = _choose_value(idx, FIELD_KEYS[label], prefer)
        probabilities[label] = prob
        return val

    out = {
        "number": pick("number"),
        "country": pick("country"),  # typically 'Nationality Code' (e.g., KEN)
        "name": pick("name"),
        "surname": pick("surname"),
        "middle name": pick("middle name"),
        "gender": pick("gender"),
        "place of birth": pick("place of birth"),
        "birth date": pick("birth date"),
        "issue date": pick("issue date"),
        "expiry date": pick("expiry date"),
        "mother name": pick("mother name"),
        "father name": pick("father name"),
        "spouse name": pick("spouse name"),
        # For issue info, try name/code aliases; fallbacks handled by pick()
        "place of issue": pick("place of issue"),
        "country of issue": pick("country of issue"),
        "mrzLine1": "",
        "mrzLine2": "",
    }

    # MRZ lines: prefer dedicated "MRZ Strings"
    mrz_key = _lower("MRZ Strings")
    mrz_block = ""
    mrz_prob = 0.0
    if mrz_key in idx and idx[mrz_key]["MRZ"]:
        # take highest-prob MRZ block for MRZ Strings
        best_mrz = max(idx[mrz_key]["MRZ"], key=lambda t: t[1] if isinstance(t[1], (int, float)) else -1)
        mrz_block = best_mrz[0]
        mrz_prob = best_mrz[1]
    elif mrz_key in idx and idx[mrz_key]["VISUAL"]:
        best_visual = max(idx[mrz_key]["VISUAL"], key=lambda t: t[1] if isinstance(t[1], (int, float)) else -1)
        mrz_block = best_visual[0]
        mrz_prob = best_visual[1]
    
    if mrz_block:
        l1, l2 = _best_mrz_lines(mrz_block)
        out["mrzLine1"], out["mrzLine2"] = l1, l2
        probabilities["mrzLine1"] = mrz_prob if l1 else 0.0
        probabilities["mrzLine2"] = mrz_prob if l2 else 0.0

    # Include probabilities in output for postprocessing and CSV export
    out["probabilities"] = probabilities
    return out
