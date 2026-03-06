"""SKILL.md frontmatter validator.

Validates a SKILL.md file against the Agent Skills specification:
- YAML frontmatter must be present and parseable
- ``name`` (required): lowercase, hyphens, max 64 chars
- ``description`` (required): max 1024 chars
- Optional fields are type-checked if present

Phase: Skills Integration
"""

from __future__ import annotations

import re
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9\-]{0,63}$")
_FRONTMATTER_FENCE = re.compile(r"^---\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_skill_frontmatter(content: str) -> dict[str, Any]:
    """Validate a SKILL.md file and return structured results.

    Parameters
    ----------
    content:
        The full text of the SKILL.md file (frontmatter + body).

    Returns
    -------
    dict with keys:
        - ``valid`` (bool)
        - ``errors`` (list[str])
        - ``warnings`` (list[str])
        - ``parsed_name`` (str | None)
        - ``parsed_description`` (str | None)
        - ``frontmatter`` (dict | None) — parsed YAML frontmatter
        - ``body`` (str | None) — Markdown body after frontmatter
    """
    errors: list[str] = []
    warnings: list[str] = []
    parsed_name: str | None = None
    parsed_description: str | None = None
    frontmatter: dict[str, Any] | None = None
    body: str | None = None

    # ── Step 1: Extract frontmatter ─────────────────────────
    fences = list(_FRONTMATTER_FENCE.finditer(content))
    if len(fences) < 2:
        errors.append("SKILL.md must start with YAML frontmatter delimited by '---'.")
        return _result(False, errors, warnings, parsed_name, parsed_description, frontmatter, body)

    yaml_text = content[fences[0].end(): fences[1].start()]
    body = content[fences[1].end():].strip()

    # ── Step 2: Parse YAML ──────────────────────────────────
    try:
        frontmatter = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        errors.append(f"YAML parse error: {exc}")
        return _result(False, errors, warnings, parsed_name, parsed_description, frontmatter, body)

    if not isinstance(frontmatter, dict):
        errors.append("Frontmatter must be a YAML mapping (key-value pairs).")
        return _result(False, errors, warnings, parsed_name, parsed_description, frontmatter, body)

    # ── Step 3: Validate required fields ─────────────────────

    # name
    name = frontmatter.get("name")
    if not name:
        errors.append("Missing required field: 'name'.")
    elif not isinstance(name, str):
        errors.append("Field 'name' must be a string.")
    elif not _NAME_PATTERN.match(name):
        errors.append(
            f"Field 'name' must be lowercase alphanumeric with hyphens, "
            f"max 64 chars. Got: '{name}'."
        )
    else:
        parsed_name = name

    # description
    description = frontmatter.get("description")
    if not description:
        errors.append("Missing required field: 'description'.")
    elif not isinstance(description, str):
        errors.append("Field 'description' must be a string.")
    elif len(description) > 1024:
        errors.append(
            f"Field 'description' exceeds 1024 characters ({len(description)})."
        )
    else:
        parsed_description = description.strip()

    # ── Step 4: Validate optional fields ─────────────────────

    # license
    lic = frontmatter.get("license")
    if lic is not None and not isinstance(lic, str):
        warnings.append("Field 'license' should be a string (e.g., SPDX identifier).")

    # compatibility
    compat = frontmatter.get("compatibility")
    if compat is not None and not isinstance(compat, str):
        warnings.append("Field 'compatibility' should be a string.")
    elif isinstance(compat, str) and len(compat) > 500:
        warnings.append("Field 'compatibility' exceeds recommended 500 characters.")

    # metadata
    meta = frontmatter.get("metadata")
    if meta is not None:
        if not isinstance(meta, dict):
            warnings.append("Field 'metadata' should be a YAML mapping.")
        else:
            for k, v in meta.items():
                if not isinstance(k, str) or not isinstance(v, (str, int, float, bool)):
                    warnings.append(
                        f"metadata key '{k}' has non-scalar value — "
                        "recommend string values for portability."
                    )

    # ── Step 5: Body warnings ────────────────────────────────

    if not body:
        warnings.append("SKILL.md body is empty — consider adding instructions.")
    elif len(body) > 20_000:
        warnings.append(
            f"SKILL.md body is {len(body)} characters — "
            "recommended max is ~5,000 tokens (~20,000 chars) for context efficiency."
        )

    valid = len(errors) == 0
    return _result(valid, errors, warnings, parsed_name, parsed_description, frontmatter, body)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _result(
    valid: bool,
    errors: list[str],
    warnings: list[str],
    parsed_name: str | None,
    parsed_description: str | None,
    frontmatter: dict[str, Any] | None,
    body: str | None,
) -> dict[str, Any]:
    return {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "parsed_name": parsed_name,
        "parsed_description": parsed_description,
        "frontmatter": frontmatter,
        "body": body,
    }


def parse_skill_content(content: str) -> tuple[dict[str, Any] | None, str]:
    """Parse a SKILL.md file into (frontmatter_dict, body_text).

    Returns ``(None, content)`` if there is no valid frontmatter.
    """
    fences = list(_FRONTMATTER_FENCE.finditer(content))
    if len(fences) < 2:
        return None, content

    yaml_text = content[fences[0].end(): fences[1].start()]
    body = content[fences[1].end():].strip()

    try:
        fm = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        return None, content

    if not isinstance(fm, dict):
        return None, content

    return fm, body
