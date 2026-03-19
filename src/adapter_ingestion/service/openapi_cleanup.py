# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any


SCHEMA_REF_PREFIX = "#/components/schemas/"


def prune_unused_schemas(schema: dict[str, Any]) -> None:
    components = schema.get("components")
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        return

    referenced = _collect_top_level_schema_refs(schema)
    kept: set[str] = set()
    pending = list(referenced)

    while pending:
        current = pending.pop()
        if current in kept:
            continue
        current_schema = schemas.get(current)
        if not isinstance(current_schema, dict):
            continue
        kept.add(current)
        pending.extend(_collect_schema_refs(current_schema))

    for schema_name in list(schemas.keys()):
        if schema_name not in kept:
            schemas.pop(schema_name, None)


def _collect_top_level_schema_refs(schema: dict[str, Any]) -> set[str]:
    trimmed = {key: value for key, value in schema.items() if key != "components"}
    return _collect_schema_refs(trimmed)


def _collect_schema_refs(node: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(node, dict):
        ref_value = node.get("$ref")
        if isinstance(ref_value, str) and ref_value.startswith(SCHEMA_REF_PREFIX):
            refs.add(ref_value[len(SCHEMA_REF_PREFIX) :])
        for value in node.values():
            refs.update(_collect_schema_refs(value))
    elif isinstance(node, list):
        for item in node:
            refs.update(_collect_schema_refs(item))
    return refs
