# SPDX-License-Identifier: EUPL-1.2
"""Compare captured workbook cells; passing is evidence only for the supplied case."""
import math


def formula_tokens(formula):
    import re
    if formula is None: return None
    tokens=re.findall(r'"(?:[^"]|"")*"|\x27(?:[^\x27]|\x27\x27)*\x27|[A-Za-z_][\w.]*|\d+(?:\.\d+)?|\S',formula)
    array="{" in tokens
    return [token if token.startswith('"') else token.upper() if array else token.upper().replace(";", ",") for token in tokens]


def compare(expected, actual, absolute=1e-9, relative=1e-9, formulas=True):
    if not all(math.isfinite(value) and value >= 0 for value in (absolute, relative)):
        raise ValueError("Comparison tolerances must be finite and nonnegative")
    differences, checked = [], 0
    for sheet in sorted(set(expected["sheets"]) | set(actual["sheets"])):
        left, right = expected["sheets"].get(sheet, {}), actual["sheets"].get(sheet, {})
        for address in sorted(set(left) | set(right)):
            checked += 1
            a, b = left.get(address), right.get(address)
            reason = None
            if a is None or b is None:
                reason = "Cell missing from capture"
            else:
                av, bv = a["value"], b["value"]
                numeric = all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in (av, bv))
                if numeric and not math.isclose(av, bv, abs_tol=absolute, rel_tol=relative): reason = "Numeric values differ"
                elif not numeric and (type(av) is not type(bv) or av != bv): reason = "Values or types differ"
                elif formulas and formula_tokens(a.get("formula")) != formula_tokens(b.get("formula")): reason = "Formulas differ"
            if reason:
                differences.append({"sheet": sheet, "cell": address, "reason": reason, "expected": a, "actual": b})
    return {"schema_version": "1", "passed": checked > 0 and not differences, "cells_checked": checked, "absolute_tolerance": absolute, "relative_tolerance": relative, "compare_formulas": formulas, "differences": differences}
