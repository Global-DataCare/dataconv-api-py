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

    def test_professional_smart_exchange_trust_settings_are_injected_into_runtime(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        for setting in (
            "SMART_GW_ALLOWED_ISSUERS",
            "SMART_GW_EXPECTED_AUDIENCES",
            "SMART_GW_ISSUER_TENANT_BINDINGS",
            "SMART_GW_DID_CACHE_TTL_SECONDS",
            "SMART_GW_HTTP_TIMEOUT_SECONDS",
            "SMART_RESEARCH_AUTH_REQUIRED_IN_DEMO",
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

    def test_ingress_can_opt_in_to_route_terminology_to_an_internal_service(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        self.assertIn('TERMINOLOGY_INGRESS_ENABLED="${PRECONV_TERMINOLOGY_INGRESS_ENABLED:-false}"', deploy_script)
        self.assertIn('TERMINOLOGY_INGRESS_SERVICE_NAME="${PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME:-}"', deploy_script)
        self.assertIn('TERMINOLOGY_INGRESS_SERVICE_PORT="${PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT:-}"', deploy_script)
        terminology_path = "          - path: /v1/terminology"
        dataconv_path = "          - path: /"
        self.assertIn(terminology_path, deploy_script)
        terminology_offset = deploy_script.index(terminology_path)
        dataconv_offset = deploy_script.index(dataconv_path, terminology_offset + len(terminology_path))
        self.assertLess(terminology_offset, dataconv_offset)
        self.assertIn('name: ${TERMINOLOGY_INGRESS_SERVICE_NAME}', deploy_script)
        self.assertIn('number: ${TERMINOLOGY_INGRESS_SERVICE_PORT}', deploy_script)

    def test_terminology_ingress_opt_in_requires_service_and_port(self) -> None:
        deploy_script = (ROOT / "scripts" / "deploy-gke.sh").read_text(encoding="utf-8")
        self.assertIn('PRECONV_TERMINOLOGY_INGRESS_ENABLED=true requires', deploy_script)
        self.assertIn('PRECONV_TERMINOLOGY_INGRESS_SERVICE_NAME', deploy_script)
        self.assertIn('PRECONV_TERMINOLOGY_INGRESS_SERVICE_PORT', deploy_script)


if __name__ == "__main__":
    unittest.main()
