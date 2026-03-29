import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from adapter_ingestion.service.auth_pkce import AUTH_JOBS, DCR_REGISTRY, PKCE_CODES, TOKENS, router


class TestPkceBackendAsyncEndpoints(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        DCR_REGISTRY.clear()
        PKCE_CODES.clear()
        TOKENS.clear()
        AUTH_JOBS.clear()
        self.base = "/publisher/cds-ES/v1/animal-care/acme/identity/auth"
        self.didcomm_meta = {
            "jws": {
                "protected": {
                    "alg": "ES384",
                    "jwk": {"kty": "EC", "crv": "P-384", "x": "x", "y": "y"},
                }
            }
        }

    def _poll(self, location: str):
        return self.client.post(location)

    def test_dcr_submit_and_poll(self):
        payload = {
            "thid": "thid-dcr-1",
            "type": "application/bundle-api+json",
            "client_id": "client-1",
            "body": {},
            "meta": self.didcomm_meta,
        }
        submit = self.client.post(f"{self.base}/_dcr", json=payload)
        self.assertEqual(submit.status_code, 202)
        location = submit.headers.get("Location")
        self.assertTrue(isinstance(location, str) and location)

        poll = self._poll(location)
        self.assertEqual(poll.status_code, 200)
        data = poll.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("action"), "_dcr")

    def test_code_submit_and_poll(self):
        self.client.post(
            f"{self.base}/_dcr",
            json={
                "thid": "thid-dcr-2",
                "type": "application/bundle-api+json",
                "client_id": "client-2",
                "body": {},
                "meta": self.didcomm_meta,
            },
        )
        submit = self.client.post(
            f"{self.base}/_code",
            json={
                "thid": "thid-code-1",
                "type": "application/bundle-api+json",
                "body": {
                    "client_id": "client-2",
                    "code_challenge": "abc",
                    "code_challenge_method": "S256",
                },
                "meta": self.didcomm_meta,
            },
        )
        self.assertEqual(submit.status_code, 202)
        poll = self._poll(submit.headers["Location"])
        self.assertEqual(poll.status_code, 200)
        self.assertIn("code", poll.json())

    def test_token_submit_and_poll(self):
        self.client.post(
            f"{self.base}/_dcr",
            json={
                "thid": "thid-dcr-3",
                "type": "application/bundle-api+json",
                "client_id": "client-3",
                "body": {},
                "meta": self.didcomm_meta,
            },
        )
        verifier = "verifier-123"
        import base64
        import hashlib
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        code_submit = self.client.post(
            f"{self.base}/_code",
            json={
                "thid": "thid-code-2",
                "type": "application/bundle-api+json",
                "body": {
                    "client_id": "client-3",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                },
                "meta": self.didcomm_meta,
            },
        )
        code_poll = self._poll(code_submit.headers["Location"])
        code = code_poll.json()["code"]

        token_submit = self.client.post(
            f"{self.base}/_token",
            json={
                "thid": "thid-token-1",
                "type": "application/bundle-api+json",
                "body": {
                    "client_id": "client-3",
                    "code": code,
                    "code_verifier": verifier,
                },
                "meta": self.didcomm_meta,
            },
        )
        self.assertEqual(token_submit.status_code, 202)
        token_poll = self._poll(token_submit.headers["Location"])
        self.assertEqual(token_poll.status_code, 200)
        data = token_poll.json()
        self.assertEqual(data.get("action"), "_token")
        self.assertIn("id_token", data)


if __name__ == "__main__":
    unittest.main()
