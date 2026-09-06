# Flow contract: reuse shared test fixtures and canonical types; do not introduce duplicated literals.
# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DeployGkeContractTests(unittest.TestCase):
    def test_cloud_sql_secret_file_is_scoped_to_the_deployment_environment(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        self.assertIn('private-cloudsql.${ENV_NAME}.env', deploy_script)
        self.assertIn('[[ "${ENV_NAME}" == "staging" || "${ENV_NAME}" == "production" ]]', deploy_script)
        self.assertLess(
            deploy_script.index('source "${PRIVATE_ENV_FILE}"'),
            deploy_script.index('source "${ENV_FILE}"'),
        )

    def test_deployment_restarts_pods_after_config_or_secret_rotation(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        self.assertIn('rollout restart deployment/"${DEPLOY_API_NAME}"', deploy_script)
        self.assertIn('rollout restart deployment/"${DEPLOY_WORKER_NAME}"', deploy_script)

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

    def test_optional_terminology_and_coding_model_settings_are_injected_into_runtime(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        for setting in (
            "PRECONV_TERMINOLOGY_BASE_URL",
            "PRECONV_TERMINOLOGY_TIMEOUT_SECONDS",
            "PRECONV_CODING_MODEL_BASE_URL",
            "PRECONV_CODING_MODEL_AUDIENCE",
            "PRECONV_CODING_MODEL_ID",
            "PRECONV_CODING_MODEL_TIMEOUT_SECONDS",
            "PRECONV_TERMINOLOGY_TOKEN",
            "PRECONV_CODING_MODEL_TOKEN",
        ):
            self.assertIn(f"--from-literal={setting}=", deploy_script)


if __name__ == "__main__":
    unittest.main()
