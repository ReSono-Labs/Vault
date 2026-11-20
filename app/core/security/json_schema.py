"""Offline JSON Schema (Draft 2020-12) checks for schemas Vault did not write.

jsonschema's default registry retrieves any ``$ref`` it cannot resolve locally
(http, https and file URIs). Schemas from MCP servers and packages are
untrusted, so every validator Vault builds uses a registry that never
retrieves, and checked schemas may only reference their own document.
"""

from __future__ import annotations

from collections.abc import Mapping

from jsonschema import Draft202012Validator
from referencing import Registry

# The default ``Registry()`` has no retrieval: an unknown URI fails to resolve.
_OFFLINE_REGISTRY: Registry = Registry()
_REFERENCE_KEYWORDS = ("$ref", "$dynamicRef")
# Values under these keywords are data, not subschemas.
_DATA_KEYWORDS = frozenset({"const", "enum", "default", "examples"})
_SCHEMA_MAP_KEYWORDS = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"})


class SchemaReferenceError(ValueError):
    """A schema refers to a document other than itself."""


def check_schema(schema: object) -> None:
    """Check a schema against Draft 2020-12 and refuse references outside it.

    Raises ``jsonschema.exceptions.SchemaError`` for an invalid schema and
    ``SchemaReferenceError`` for a remote, file or other absolute reference.
    """
    Draft202012Validator.check_schema(schema)
    _refuse_external_references(schema)


def offline_validator(schema: Mapping[str, object] | bool) -> Draft202012Validator:
    """A validator that resolves only in-document references and never fetches."""
    return Draft202012Validator(schema, registry=_OFFLINE_REGISTRY)


def _refuse_external_references(node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _refuse_external_references(item)
        return
    if not isinstance(node, dict):
        return
    for keyword in _REFERENCE_KEYWORDS:
        reference = node.get(keyword)
        if isinstance(reference, str) and not reference.startswith("#"):
            raise SchemaReferenceError(
                f"Schema {keyword} must point inside the same schema (#/...); "
                "references to other documents are not allowed"
            )
    for key, value in node.items():
        if key in _SCHEMA_MAP_KEYWORDS and isinstance(value, dict):
            # Keys here are names chosen by the schema author, values are schemas.
            for subschema in value.values():
                _refuse_external_references(subschema)
        elif key not in _DATA_KEYWORDS:
            _refuse_external_references(value)
