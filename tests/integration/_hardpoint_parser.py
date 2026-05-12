"""Tiny regex-based extractor for ships/Hardpoints/<name>.py.

Each hardpoint file is a sequence of `Template = Property_Create("Name")`
followed by a block of `Template.SetFoo(value)` lines. This extractor
finds a named template and returns a dict of setter-name -> Python value.

Values are parsed as int / float / quoted-string. Non-literal call
arguments (e.g. `Hardpoint.SetDirection(kDirection)`) are recorded as
the raw string; tests usually only care about scalar fields.
"""
from __future__ import annotations

import re
from pathlib import Path


_TEMPLATE_RE = re.compile(r"^(\w+)\s*=\s*App\.\w+_Create\(")
_SETTER_RE = re.compile(r"^(\w+)\.Set(\w+)\(([^)]*)\)")


def _parse_value(raw: str):
    s = raw.strip()
    if not s:
        return None
    # Try int
    try:
        return int(s)
    except ValueError:
        pass
    # Try float (covers "120.000000")
    try:
        return float(s)
    except ValueError:
        pass
    # Quoted string?
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # Fallback: raw text (likely a variable reference)
    return s


def extract_setters(path: Path, template_name: str) -> dict:
    """Return {setter_name: value} for all `template_name.SetX(...)` lines.

    Raises KeyError if template_name is never declared in the file.
    """
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    declared = False
    setters: dict = {}
    for line in text.splitlines():
        m = _TEMPLATE_RE.match(line.strip())
        if m and m.group(1) == template_name:
            declared = True
        m2 = _SETTER_RE.match(line.strip())
        if m2 and m2.group(1) == template_name:
            name, args = m2.group(2), m2.group(3)
            # Single-arg setter: store directly. Multi-arg (e.g.
            # SetMaxShields(face, value), SetShieldChargePerSecond(face, value))
            # store as list of (key, value) tuples accumulated under the name.
            parts = [_parse_value(p) for p in args.split(",")]
            if len(parts) == 1:
                setters[name] = parts[0]
            else:
                setters.setdefault(name, []).append(tuple(parts))
    if not declared:
        raise KeyError(f"Template {template_name!r} not declared in {path}")
    return setters
