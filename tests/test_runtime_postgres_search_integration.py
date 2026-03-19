# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
import os
import sys
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from adapter_ingestion.runtime.adapters import PostgresSearchRepository


class PostgresSearchIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.getenv("RUN_POSTGRES_INTEGRATION", "").strip() != "1":
            raise unittest.SkipTest("Set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL search integration tests.")

        dsn = str(os.getenv("POSTGRES_DSN", "")).strip()
        if not dsn:
            raise unittest.SkipTest("POSTGRES_DSN is required for PostgreSQL integration tests.")

        cls.table_name = f"resource_search_index_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        cls.repo = PostgresSearchRepository(dsn=dsn, table_name=cls.table_name)
        cls.vault_id = f"itest-vault-{uuid.uuid4().hex[:8]}"

    @classmethod
    def tearDownClass(cls) -> None:
        repo = getattr(cls, "repo", None)
        if repo is None:
            return
        with repo._connect() as conn:  # noqa: SLF001 - integration cleanup against ephemeral table
            with conn.cursor() as cur:
                cur.execute(f'DROP TABLE IF EXISTS "{cls.table_name}"')
            conn.commit()

    def test_upsert_search_and_delete_roundtrip(self) -> None:
        composition = {
            "resourceType": "Composition",
            "id": f"comp-{uuid.uuid4().hex[:8]}",
            "meta": {
                "claims": {
                    "Composition.userSelected": "false",
                    "Composition.relatesto-target": "itest-thid-001",
                    "Composition.relatesto-type": "part-of",
                    "Composition.date": "2026-03-15T09:23:19Z",
                }
            },
        }

        self.assertTrue(
            self.repo.upsert(
                vault_id=self.vault_id,
                resource_type="Composition",
                resource=composition,
            )
        )

        by_user_selected = self.repo.search(
            vault_id=self.vault_id,
            resource_type="Composition",
            search_params={"userselected": "false"},
        )
        self.assertEqual(len(by_user_selected), 1)
        self.assertEqual(by_user_selected[0]["id"], composition["id"])

        by_target = self.repo.search(
            vault_id=self.vault_id,
            resource_type="Composition",
            search_params={"relatesto-target": "itest-thid-001"},
        )
        self.assertEqual(len(by_target), 1)
        self.assertEqual(by_target[0]["id"], composition["id"])

        self.assertTrue(
            self.repo.delete(
                vault_id=self.vault_id,
                resource_type="Composition",
                resource_id=composition["id"],
            )
        )
        self.assertEqual(
            self.repo.search(
                vault_id=self.vault_id,
                resource_type="Composition",
                search_params={"userselected": "false"},
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
