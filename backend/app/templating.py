"""Minimal ``{{variable}}`` templating engine.

This is deliberately NOT a full template language (no conditionals, loops, filters, or
expressions) -- just literal ``{{name}}`` substitution. A variable name is any run of
characters matched by ``[A-Za-z0-9_]+``, optionally padded with whitespace inside the
braces (``{{ name }}`` is equivalent to ``{{name}}``).

Escaping rule
-------------
Prompts frequently embed JSON examples that themselves contain double-brace-like syntax
(e.g. Python's ``f"{{...}}"`` inside an example, or a literal JSON object shown as
sample output). To let a prompt author include a literal ``{{`` / ``}}`` that must NOT
be treated as a variable placeholder, escape it by doubling: ``{{{{`` renders as a
literal ``{{`` and ``}}}}`` renders as a literal ``}}``. This mirrors the escaping
convention used by Python's ``str.format`` / Jinja2, which prompt authors are likely
already familiar with, and keeps the placeholder grammar unambiguous: a real
placeholder is always exactly two braces around a bare variable name, never four.

Only a run of EXACTLY two braces containing a bare identifier (optionally
whitespace-padded) is treated as a placeholder. Anything else -- stray single braces,
four-brace escapes, or ``{{...}}`` containing non-identifier characters (e.g. JSON like
``{{"key": "value"}}``) -- is left untouched as literal text. This means most JSON
examples "just work" without any escaping at all, since ``{{"key"...`` does not match
the identifier-only placeholder pattern; the doubled-brace escape exists for the rarer
case where a literal ``{{name}}``-shaped token must appear verbatim.
"""

from __future__ import annotations

import re

_ESCAPED_OPEN = "\x00PROMPTLAB_LBRACE\x00"
_ESCAPED_CLOSE = "\x00PROMPTLAB_RBRACE\x00"

# A placeholder is {{ident}} where ident is [A-Za-z0-9_]+, with optional surrounding
# whitespace inside the braces. Must not itself be part of a {{{{ / }}}} escape run --
# that is handled by pre-extracting escapes before this pattern is applied.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


class MissingVariables(list[str]):
    """A list of variable names referenced by a template but absent from the provided inputs.

    Subclasses ``list`` so callers can use it both as a boolean truthiness check
    (``if missing:``) and as an ordered collection of the missing names.
    """


def _protect_escapes(template: str) -> str:
    """Replace ``{{{{`` / ``}}}}`` escape runs with sentinel placeholders."""
    return template.replace("{{{{", _ESCAPED_OPEN).replace("}}}}", _ESCAPED_CLOSE)


def _restore_escapes(text: str) -> str:
    """Turn sentinel placeholders back into literal ``{{`` / ``}}``."""
    return text.replace(_ESCAPED_OPEN, "{{").replace(_ESCAPED_CLOSE, "}}")


def extract_variables(template: str) -> list[str]:
    """Return the ordered, de-duplicated list of variable names referenced in ``template``.

    Tolerant of whitespace inside braces (``{{ name }}``). Ignores four-brace escape
    runs (``{{{{...}}}}``) entirely -- they never produce a variable name.
    """
    protected = _protect_escapes(template)
    seen: dict[str, None] = {}
    for match in _PLACEHOLDER_RE.finditer(protected):
        name = match.group(1)
        seen.setdefault(name, None)
    return list(seen.keys())


def render(template: str, inputs: dict[str, str]) -> str:
    """Substitute every ``{{variable}}`` in ``template`` with its value from ``inputs``.

    Raises :class:`KeyError`-style :class:`ValueError` (via :func:`validate`) semantics:
    a ``{{var}}`` with no matching key in ``inputs`` is an error, NOT silently rendered
    as an empty string. Call :func:`validate` first if you want to collect all missing
    variables at once instead of failing on the first one.
    """
    missing = validate(template, set(inputs.keys()))
    if missing:
        raise ValueError(f"Missing template variables: {', '.join(missing)}")

    protected = _protect_escapes(template)

    def _sub(match: re.Match[str]) -> str:
        return str(inputs[match.group(1)])

    rendered = _PLACEHOLDER_RE.sub(_sub, protected)
    return _restore_escapes(rendered)


def validate(template: str, available_vars: set[str] | list[str]) -> MissingVariables:
    """Return the variables ``template`` references that are absent from ``available_vars``.

    An empty :class:`MissingVariables` (falsy) means the template's needs are fully
    satisfied.
    """
    available = set(available_vars)
    required = extract_variables(template)
    return MissingVariables(v for v in required if v not in available)
