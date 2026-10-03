"""Value-free shapes of JSON payloads, and the check that the league's payloads match CFBD's.

A shape records, for every path in a payload, the JSON types seen there and the keys of every
object: nothing else. The shapes of the private recordings are kept in
tests/fixtures/league/shapes.json (public: field names and types are CFBD's published schema), and
the league's twin of each recording must fit its shape.
"""

from __future__ import annotations

from typing import Any


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    return "dict"


def shape_of(value: Any, shape: dict | None = None, limit: int = 600) -> dict:
    """Merge `value` into `shape` (t: types, k: object keys, i: list items)."""
    shape = shape if shape is not None else {}
    kind = json_type(value)
    types = set(shape.get("t", []))
    types.add(kind)
    shape["t"] = sorted(types)
    if kind == "dict":
        keys = shape.setdefault("k", {})
        for k, v in value.items():
            keys[k] = shape_of(v, keys.get(k), limit)
    elif kind == "list":
        item = shape.get("i")
        for v in value[:limit]:
            item = shape_of(v, item, limit)
        if item is not None:
            shape["i"] = item
    return shape


NUMERIC = {"int", "float"}


def _kind(t: str) -> str:
    """Types as the check compares them: JSON numbers are one kind, and null fits anywhere (one
    recorded game sends a null where another sends a value, and the app guards both)."""
    return "number" if t in NUMERIC else t


def compare(expected: dict, actual: dict, path: str = "$") -> list[str]:
    """Problems with `actual` (the league's shape) against `expected` (CFBD's). Keys CFBD sent that
    the league lacks, keys the league invents, and types CFBD never sent there. An int where CFBD
    sent floats is fine (JSON numbers), so is a null either way, and so is a branch where either
    side had no data."""
    problems: list[str] = []
    exp_t = {_kind(t) for t in expected.get("t", [])} - {"null"}
    act_t = {_kind(t) for t in actual.get("t", [])} - {"null"}
    stray = act_t - exp_t
    if stray and exp_t:
        problems.append(f"{path}: type {sorted(stray)} where CFBD sends {sorted(exp_t)}")
    if "k" in expected and "k" in actual:
        exp_k, act_k = expected["k"], actual["k"]
        for key in exp_k:
            if key not in act_k:
                problems.append(f"{path}.{key}: missing")
        for key in act_k:
            if key not in exp_k:
                problems.append(f"{path}.{key}: not a CFBD field")
        for key in exp_k:
            if key in act_k:
                problems.extend(compare(exp_k[key], act_k[key], f"{path}.{key}"))
    if "i" in expected and "i" in actual:
        problems.extend(compare(expected["i"], actual["i"], f"{path}[]"))
    return problems
