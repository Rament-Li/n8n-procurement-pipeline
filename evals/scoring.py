"""Scoring for the procurement email extraction evals.

Pure functions only. Nothing here touches the network, the environment or any credential,
so it can be tested offline.
"""
import json
import re

FIELDS = ["docType", "supplier", "order_ref", "status", "order_date", "currency", "items"]


def norm(value):
    """Lower-case letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def norm_ref(value):
    """Upper-case letters and digits only, matching how the workflow normalises order references."""
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def parse_model_json(text):
    """Return a dict parsed from the model output, or None if it is not valid JSON."""
    if not isinstance(text, str):
        return None
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.I).strip()
    try:
        data = json.loads(cleaned)
    except ValueError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(cleaned[start:end + 1])
        except ValueError:
            return None
    return data if isinstance(data, dict) else None


def _accepted(expected):
    return expected if isinstance(expected, list) else [expected]


def _text_match(got, expected, fn):
    return any(fn(got) == fn(e) for e in _accepted(expected))


def _supplier_match(got, expected):
    a = norm(got)
    for e in _accepted(expected):
        b = norm(e)
        if a == b or (a and b and (a in b or b in a)):
            return True
    return False


def _quantity(value):
    m = re.search(r"\d+(?:\.\d+)?", str(value if value is not None else ""))
    return float(m.group()) if m else None


def score_items(got_items, expected_items):
    """Pass when the number of items is right and every expected item is found.

    An expected item is found when the returned SKU matches exactly, or, if the model returned
    no SKU, the expected product name appears in the returned product name. The quantity must
    also match when one is expected.
    """
    if not isinstance(got_items, list) or len(got_items) != len(expected_items):
        return False
    remaining = [g for g in got_items if isinstance(g, dict)]
    if len(remaining) != len(expected_items):
        return False
    for exp in expected_items:
        found = None
        for got in remaining:
            got_sku = norm_ref(got.get("sku"))
            if exp.get("sku") and got_sku:
                ident_ok = got_sku == norm_ref(exp["sku"])  # a returned SKU must match exactly
            else:
                ident_ok = bool(exp.get("product")) and norm(exp["product"]) in norm(got.get("product"))
            qty_ok = exp.get("quantity") is None or _quantity(got.get("quantity")) == float(exp["quantity"])
            if ident_ok and qty_ok:
                found = got
                break
        if found is None:
            return False
        remaining.remove(found)
    return True


def score_case(output, expected):
    """Score one parsed model output against the expected answer.

    Returns {"invalid_json": bool, "fields": {field: bool}, "passed": bool}.
    A field whose expected value is None is not scored for that case.
    """
    scored = [f for f in FIELDS if f in expected and expected[f] is not None]
    if output is None:
        return {"invalid_json": True, "fields": {f: False for f in scored}, "passed": False}
    results = {}
    for f in scored:
        exp, got = expected[f], output.get(f)
        if f == "docType":
            results[f] = _text_match(got, exp, norm)
        elif f == "supplier":
            results[f] = _supplier_match(got, exp)
        elif f == "order_ref":
            results[f] = _text_match(got, exp, norm_ref)
        elif f == "status":
            results[f] = _text_match(got, exp, norm)
        elif f == "order_date":
            results[f] = str(got or "").strip() == str(exp).strip()
        elif f == "currency":
            results[f] = _text_match(got, exp, norm)
        elif f == "items":
            results[f] = score_items(got, exp)
    return {"invalid_json": False, "fields": results, "passed": all(results.values())}


def summarise(case_results):
    """Aggregate a list of score_case() dicts into overall and per-field accuracy."""
    total = len(case_results)
    field_hits = {f: [0, 0] for f in FIELDS}
    for r in case_results:
        for f, ok in r["fields"].items():
            field_hits[f][1] += 1
            field_hits[f][0] += int(ok)
    return {
        "cases": total,
        "passed": sum(1 for r in case_results if r["passed"]),
        "invalid_json": sum(1 for r in case_results if r["invalid_json"]),
        "fields": {f: {"correct": c, "scored": n} for f, (c, n) in field_hits.items() if n},
    }
