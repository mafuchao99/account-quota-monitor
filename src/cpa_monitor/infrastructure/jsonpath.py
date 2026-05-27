from __future__ import annotations

from typing import Any


def get_path(payload: Any, path: str | None, default: Any = None) -> Any:
    if not path:
        return default
    if path == "$":
        return payload
    if not path.startswith("$."):
        raise ValueError(f"Only simple $.a.b[0] JSON paths are supported: {path}")
    current = payload
    for token in _tokenize(path[2:]):
        if isinstance(token, int):
            if not isinstance(current, list) or token >= len(current):
                return default
            current = current[token]
        else:
            if not isinstance(current, dict) or token not in current:
                return default
            current = current[token]
    return current


def _tokenize(path: str) -> list[str | int]:
    tokens: list[str | int] = []
    for part in path.split("."):
        while "[" in part:
            name, rest = part.split("[", 1)
            if name:
                tokens.append(name)
            index, part = rest.split("]", 1)
            tokens.append(int(index))
            if part.startswith("."):
                part = part[1:]
        if part:
            tokens.append(part)
    return tokens


def to_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    return int(value)


def to_float_or_none(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    return float(value)
