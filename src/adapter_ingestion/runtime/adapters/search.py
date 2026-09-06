# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any
import copy
import json
import re

from gdc_data_utils import canonical_claim_for_search_parameter, storage_key_for_claim

from ..ports import ISearchRepository


def _normalize_search_token(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "_", str(value or "").strip().lower()).strip("_")


def _search_field_name(resource_type: str, field_name: str) -> str:
    resource = str(resource_type or "").strip()
    field = str(field_name or "").strip()
    if resource and field:
        return storage_key_for_claim(
            canonical_claim_for_search_parameter(resource, field)
        )
    return _normalize_search_token(resource or field)


def _claims(resource: dict[str, Any]) -> dict[str, Any]:
    meta = resource.get("meta", {})
    if not isinstance(meta, dict):
        return {}
    claims = meta.get("claims", {})
    if not isinstance(claims, dict):
        return {}
    return claims


def _search_fields(resource: dict[str, Any]) -> dict[str, str]:
    resource_type = str(resource.get("resourceType", "")).strip()
    claims = _claims(resource)
    fields: dict[str, str] = {}
    for existing_key, existing_value in claims.items():
        claim_key = str(existing_key or "").strip()
        if not claim_key or claim_key.startswith("@"):
            continue
        claim_value = str(existing_value or "")
        if "." in claim_key:
            claim_resource_type, claim_field_name = claim_key.split(".", 1)
            fields[storage_key_for_claim(claim_key)] = claim_value
            if _normalize_search_token(claim_resource_type) == _normalize_search_token(resource_type):
                fields[_normalize_search_token(claim_field_name)] = claim_value
            continue
        fields[_search_field_name(resource_type, claim_key)] = claim_value
        fields[_normalize_search_token(claim_key)] = claim_value
    return fields


def _search_field_value(resource: dict[str, Any], resource_type: str, field_name: str) -> str:
    search_fields = _search_fields(resource)
    if str(field_name or "").strip().endswith(":text"):
        base_name = str(field_name or "").strip().split(":", 1)[0]
        display_value = search_fields.get(
            _search_field_name(resource_type, f"{base_name}-display"), ""
        )
        if display_value:
            return str(display_value)
    direct = search_fields.get(_search_field_name(resource_type, field_name), "")
    if direct:
        return str(direct or "")
    return str(search_fields.get(_normalize_search_token(field_name), "") or "")


def _search_criteria(value: Any) -> list[str]:
    values = value if isinstance(value, list) else [value]
    return [str(item or "").strip() for item in values if str(item or "").strip()]


def _matches_criterion(actual: str, field_name: str, expected: str) -> bool:
    alternatives = [item.strip() for item in expected.split(",") if item.strip()]
    for alternative in alternatives:
        if alternative.startswith(("ge", "le", "gt", "lt")):
            operator = alternative[:2]
            target = alternative[2:]
            if not actual:
                continue
            if operator == "ge" and actual >= target:
                return True
            if operator == "le" and actual <= target:
                return True
            if operator == "gt" and actual > target:
                return True
            if operator == "lt" and actual < target:
                return True
            continue
        if str(field_name or "").endswith(":text"):
            if alternative.casefold() in actual.casefold():
                return True
            continue
        if actual == alternative:
            return True
    return False


def _matches_search(resource: dict[str, Any], resource_type: str, search_params: dict[str, Any]) -> bool:
    for key, value in search_params.items():
        actual = _search_field_value(resource, resource_type, str(key or "").strip())
        for expected in _search_criteria(value):
            if not _matches_criterion(actual, str(key or "").strip(), expected):
                return False
    return True


class InMemorySearchRepository(ISearchRepository):
    def __init__(self) -> None:
        self._items: dict[str, dict[str, dict[str, dict[str, Any]]]] = {}

    def upsert(self, *, vault_id: str, resource_type: str, resource: dict[str, Any]) -> bool:
        resource_id = str(resource.get("id", "") or "").strip()
        if not vault_id or not resource_type or not resource_id:
            return False
        vault_bucket = self._items.setdefault(vault_id, {})
        type_bucket = vault_bucket.setdefault(resource_type, {})
        type_bucket[resource_id] = copy.deepcopy(resource)
        return True

    def search(
        self,
        *,
        vault_id: str,
        resource_type: str,
        search_params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        vault_bucket = self._items.get(vault_id, {})
        type_bucket = vault_bucket.get(resource_type, {})
        return [
            copy.deepcopy(resource)
            for resource in type_bucket.values()
            if _matches_search(resource, resource_type, search_params)
        ]

    def delete(self, *, vault_id: str, resource_type: str, resource_id: str) -> bool:
        vault_bucket = self._items.get(vault_id, {})
        type_bucket = vault_bucket.get(resource_type, {})
        return type_bucket.pop(resource_id, None) is not None


class PostgresSearchRepository(ISearchRepository):
    def __init__(self, *, dsn: str, table_name: str = "resource_search_index") -> None:
        try:
            import psycopg
            from psycopg import sql
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Missing dependency psycopg. Install with: pip install 'adapter-ingestion-py[postgres]'"
            ) from exc

        self._psycopg = psycopg
        self._sql = sql
        self._dsn = dsn
        self._table_name = table_name
        self._ensure_schema()

    def _connect(self):
        return self._psycopg.connect(self._dsn)

    def _ensure_schema(self) -> None:
        query = self._sql.SQL(
            """
            CREATE TABLE IF NOT EXISTS {table_name} (
                vault_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                claims JSONB NOT NULL,
                search_fields JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                resource JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (vault_id, resource_type, resource_id)
            )
            """
        ).format(table_name=self._sql.Identifier(self._table_name))
        alter_query = self._sql.SQL(
            """
            ALTER TABLE {table_name}
            ADD COLUMN IF NOT EXISTS search_fields JSONB NOT NULL DEFAULT '{{}}'::jsonb
            """
        ).format(table_name=self._sql.Identifier(self._table_name))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                cur.execute(alter_query)
            conn.commit()

    def upsert(self, *, vault_id: str, resource_type: str, resource: dict[str, Any]) -> bool:
        resource_id = str(resource.get("id", "") or "").strip()
        if not vault_id or not resource_type or not resource_id:
            return False
        claims = {}
        meta = resource.get("meta", {})
        if isinstance(meta, dict) and isinstance(meta.get("claims"), dict):
            claims = meta.get("claims", {})
        search_fields = _search_fields(resource)
        query = self._sql.SQL(
            """
            INSERT INTO {table_name} (vault_id, resource_type, resource_id, claims, search_fields, resource)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb)
            ON CONFLICT (vault_id, resource_type, resource_id)
            DO UPDATE SET claims = EXCLUDED.claims, search_fields = EXCLUDED.search_fields, resource = EXCLUDED.resource, updated_at = NOW()
            """
        ).format(table_name=self._sql.Identifier(self._table_name))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        vault_id,
                        resource_type,
                        resource_id,
                        json.dumps(claims),
                        json.dumps(search_fields),
                        json.dumps(resource),
                    ),
                )
            conn.commit()
        return True

    def search(
        self,
        *,
        vault_id: str,
        resource_type: str,
        search_params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        clauses: list[Any] = [self._sql.SQL("vault_id = %s"), self._sql.SQL("resource_type = %s")]
        values: list[Any] = [vault_id, resource_type]
        for key, value in search_params.items():
            search_field = _search_field_name(resource_type, str(key or "").strip())
            for expected in _search_criteria(value):
                alternatives = [item.strip() for item in expected.split(",") if item.strip()]
                comparisons: list[Any] = []
                comparison_values: list[Any] = []
                for alternative in alternatives:
                    if alternative.startswith(("ge", "le", "gt", "lt")):
                        operator = {"ge": ">=", "le": "<=", "gt": ">", "lt": "<"}[
                            alternative[:2]
                        ]
                        comparisons.append(
                            self._sql.SQL("field.value {} %s").format(self._sql.SQL(operator))
                        )
                        comparison_values.append(alternative[2:])
                    elif str(key or "").strip().endswith(":text"):
                        comparisons.append(
                            self._sql.SQL("position(lower(%s) in lower(field.value)) > 0")
                        )
                        comparison_values.append(alternative)
                    else:
                        comparisons.append(self._sql.SQL("field.value = %s"))
                        comparison_values.append(alternative)
                if not comparisons:
                    continue
                clauses.append(
                    self._sql.SQL(
                        """
                        EXISTS (
                            SELECT 1
                            FROM jsonb_each_text(search_fields) AS field(key, value)
                            WHERE lower(field.key) = lower(%s) AND ({})
                        )
                        """
                    ).format(self._sql.SQL(" OR ").join(comparisons))
                )
                values.extend([search_field, *comparison_values])
        query = self._sql.SQL("SELECT resource FROM {table_name} WHERE ").format(
            table_name=self._sql.Identifier(self._table_name)
        ) + self._sql.SQL(" AND ").join(clauses)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, values)
                rows = cur.fetchall()
        return [row[0] for row in rows if row and isinstance(row[0], dict)]

    def delete(self, *, vault_id: str, resource_type: str, resource_id: str) -> bool:
        query = self._sql.SQL(
            "DELETE FROM {table_name} WHERE vault_id = %s AND resource_type = %s AND resource_id = %s"
        ).format(table_name=self._sql.Identifier(self._table_name))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (vault_id, resource_type, resource_id))
                deleted = cur.rowcount > 0
            conn.commit()
        return deleted
