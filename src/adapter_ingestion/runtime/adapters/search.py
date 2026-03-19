# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any
import copy
import json

from ..ports import ISearchRepository


def _claim_value(resource: dict[str, Any], claim_key: str) -> str:
    meta = resource.get("meta", {})
    if not isinstance(meta, dict):
        return ""
    claims = meta.get("claims", {})
    if not isinstance(claims, dict):
        return ""
    direct = claims.get(claim_key, "")
    if direct:
        return str(direct or "")
    lowered_claim_key = claim_key.lower()
    for existing_key, existing_value in claims.items():
        if str(existing_key or "").strip().lower() == lowered_claim_key:
            return str(existing_value or "")
    return ""


def _matches_search(resource: dict[str, Any], resource_type: str, search_params: dict[str, Any]) -> bool:
    for key, value in search_params.items():
        expected = str(value or "").strip()
        if not expected:
            continue
        actual = _claim_value(resource, f"{resource_type}.{str(key or '').strip()}")
        if expected.startswith(("ge", "le", "gt", "lt")):
            operator = expected[:2]
            target = expected[2:]
            if not actual:
                return False
            if operator == "ge" and actual < target:
                return False
            if operator == "le" and actual > target:
                return False
            if operator == "gt" and actual <= target:
                return False
            if operator == "lt" and actual >= target:
                return False
            continue
        if actual != expected:
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
                resource JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (vault_id, resource_type, resource_id)
            )
            """
        ).format(table_name=self._sql.Identifier(self._table_name))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
            conn.commit()

    def upsert(self, *, vault_id: str, resource_type: str, resource: dict[str, Any]) -> bool:
        resource_id = str(resource.get("id", "") or "").strip()
        if not vault_id or not resource_type or not resource_id:
            return False
        claims = {}
        meta = resource.get("meta", {})
        if isinstance(meta, dict) and isinstance(meta.get("claims"), dict):
            claims = meta.get("claims", {})
        query = self._sql.SQL(
            """
            INSERT INTO {table_name} (vault_id, resource_type, resource_id, claims, resource)
            VALUES (%s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (vault_id, resource_type, resource_id)
            DO UPDATE SET claims = EXCLUDED.claims, resource = EXCLUDED.resource, updated_at = NOW()
            """
        ).format(table_name=self._sql.Identifier(self._table_name))
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (vault_id, resource_type, resource_id, json.dumps(claims), json.dumps(resource)))
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
            expected = str(value or "").strip()
            if not expected:
                continue
            claim_key = f"{resource_type}.{str(key or '').strip()}"
            if expected.startswith(("ge", "le", "gt", "lt")):
                operator = {"ge": ">=", "le": "<=", "gt": ">", "lt": "<"}[expected[:2]]
                clauses.append(
                    self._sql.SQL(
                        """
                        EXISTS (
                            SELECT 1
                            FROM jsonb_each_text(claims) AS claim(key, value)
                            WHERE lower(claim.key) = lower(%s) AND claim.value {} %s
                        )
                        """
                    ).format(self._sql.SQL(operator))
                )
                values.extend([claim_key, expected[2:]])
            else:
                clauses.append(
                    self._sql.SQL(
                        """
                        EXISTS (
                            SELECT 1
                            FROM jsonb_each_text(claims) AS claim(key, value)
                            WHERE lower(claim.key) = lower(%s) AND claim.value = %s
                        )
                        """
                    )
                )
                values.extend([claim_key, expected])
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
