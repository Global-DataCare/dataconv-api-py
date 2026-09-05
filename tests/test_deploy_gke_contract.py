# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeployGkeContractTests(unittest.TestCase):
    def test_secure_oidc_exchange_settings_are_injected_into_runtime(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        for setting in (
            "EXCHANGE_ALLOW_INSECURE_ASSERTIONS",
            "EXCHANGE_OIDC_ISSUER",
            "EXCHANGE_OIDC_AUDIENCE",
            "EXCHANGE_OIDC_ALLOWED_ISSUERS",
            "EXCHANGE_OIDC_ALLOWED_AUDIENCES",
            "EXCHANGE_SESSION_TOKEN_SECRET",
        ):
            self.assertIn(f"--from-literal={setting}=", deploy_script)


if __name__ == "__main__":
    unittest.main()
