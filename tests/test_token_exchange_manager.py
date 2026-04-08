from __future__ import annotations

from types import SimpleNamespace
import unittest

from adapter_ingestion.service.managers.token_exchange import TokenExchangeManager


def _settings(*, allow_exception: bool) -> SimpleNamespace:
    return SimpleNamespace(
        exchange_allow_api_key=True,
        exchange_allow_api_key_exception=allow_exception,
        exchange_api_keys=("demo-key",),
        exchange_api_key_subject_default="did:web:clinic.local:service:excel-uploader",
        exchange_api_key_org_default="VATES-A00000001",
        exchange_default_allowed_scopes="dataconv.upload dataconv.read",
        exchange_session_token_secret="test-session-secret",
        exchange_session_token_ttl_seconds=900,
        default_issuer_did="did:web:issuer.example",
        default_audience_did="did:web:audience.example",
        demo_mode=True,
        exchange_allow_insecure_assertions=True,
    )


class TokenExchangeManagerTests(unittest.TestCase):
    def test_api_key_exception_profile_accepts_missing_subject_token_when_enabled(self) -> None:
        manager = TokenExchangeManager(_settings(allow_exception=True))
        result = manager.exchange(
            {
                "api_key_profile": "api-key-exception.v1",
                "api_key": "demo-key",
                "organization": "VATES-A00000001",
                "scope": "dataconv.upload",
            },
            audience="http://localhost/exchange",
        )
        self.assertEqual(result.token_type, "Bearer")
        self.assertEqual(result.organization, "VATES-A00000001")
        self.assertIn("dataconv.upload", result.scope)

    def test_api_key_without_subject_token_requires_exception_profile(self) -> None:
        manager = TokenExchangeManager(_settings(allow_exception=True))
        with self.assertRaisesRegex(ValueError, "subject_token is required unless api_key_profile=api-key-exception.v1"):
            manager.exchange(
                {
                    "api_key": "demo-key",
                    "organization": "VATES-A00000001",
                    "scope": "dataconv.upload",
                },
                audience="http://localhost/exchange",
            )

    def test_api_key_exception_profile_rejected_when_disabled(self) -> None:
        manager = TokenExchangeManager(_settings(allow_exception=False))
        with self.assertRaisesRegex(ValueError, "api-key-exception.v1 is not enabled"):
            manager.exchange(
                {
                    "api_key_profile": "api-key-exception.v1",
                    "api_key": "demo-key",
                    "organization": "VATES-A00000001",
                    "scope": "dataconv.upload",
                },
                audience="http://localhost/exchange",
            )


if __name__ == "__main__":
    unittest.main()
