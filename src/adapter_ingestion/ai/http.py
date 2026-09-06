# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any, Callable, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .base import CodingSuggestion
from .terminology import CodingRankRequest, TerminologyCandidate, TerminologySearchRequest


class JsonTransport(Protocol):
    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class UrlLibJsonTransport:
    def __init__(self, *, timeout_seconds: int = 15) -> None:
        self._timeout_seconds = timeout_seconds

    def request(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url=url, method=method, headers=headers, data=payload)
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310 - configured service URL
            parsed = json.loads(response.read().decode("utf-8"))
        if not isinstance(parsed, dict):
            raise RuntimeError("service response must be a JSON object")
        return parsed


def google_audience_token_provider(audience: str) -> Callable[[], str]:
    target = str(audience or "").strip()

    def _token() -> str:
        if not target:
            return ""
        try:
            from google.auth.transport.requests import Request as GoogleAuthRequest
            from google.oauth2.id_token import fetch_id_token
        except ImportError as exc:  # pragma: no cover - production dependency guard
            raise RuntimeError("google-auth is required for audience-authenticated model calls") from exc
        return str(fetch_id_token(GoogleAuthRequest(), target) or "")

    return _token


class _AuthorizedClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str = "",
        token_provider: Callable[[], str] | None = None,
        transport: JsonTransport | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self._base_url = str(base_url or "").rstrip("/")
        self._token = str(token or "").strip()
        self._token_provider = token_provider
        self._transport = transport or UrlLibJsonTransport(timeout_seconds=timeout_seconds)

    def _headers(self) -> dict[str, str]:
        token = self._token or (str(self._token_provider() or "").strip() if self._token_provider else "")
        headers = {"accept": "application/vnd.api+json", "content-type": "application/vnd.api+json"}
        if token:
            headers["authorization"] = f"Bearer {token}"
        return headers


class HttpTerminologyClient(_AuthorizedClient):
    def search(self, request: TerminologySearchRequest) -> list[TerminologyCandidate]:
        query = urlencode(
            {
                "text": request.text,
                "language": request.language,
                "fhirVersion": request.fhir_version,
                "sector": request.sector,
                "jurisdiction": request.jurisdiction,
                "resourceType": request.resource_type,
                "field": request.field,
                "limit": request.limit,
            }
        )
        document = self._transport.request(
            method="GET",
            url=f"{self._base_url}/v1/terminology/candidates?{query}",
            headers=self._headers(),
        )
        candidates: list[TerminologyCandidate] = []
        for resource in document.get("data", []):
            if not isinstance(resource, dict):
                continue
            system = str(resource.get("id", "")).strip()
            attributes = resource.get("attributes", {})
            meta = resource.get("meta", {})
            sources = meta.get("sources", []) if isinstance(meta, dict) else []
            source = ",".join(str(value) for value in sources if str(value).strip())
            if not system or not isinstance(attributes, dict):
                continue
            for code, display in attributes.items():
                if str(code).strip() and str(display).strip():
                    candidates.append(
                        TerminologyCandidate(
                            system=system,
                            code=str(code),
                            display=str(display),
                            source=source,
                        )
                    )
        return candidates


class HttpCodingModelClient(_AuthorizedClient):
    """Ranks a closed candidate set and receives explicit human corrections."""

    def __init__(self, *, model: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model = str(model or "").strip()

    def rank(self, request: CodingRankRequest) -> list[CodingSuggestion]:
        attributes = {
            "model": self._model,
            "task": "rank-terminology-candidates",
            "text": request.text,
            "language": request.language,
            "sector": request.sector,
            "jurisdiction": request.jurisdiction,
            "subjectKind": request.subject_kind,
            "resourceType": request.resource_type,
            "field": request.field,
            "rowContext": request.row_context,
            "candidates": [
                {
                    "id": item.candidate_id,
                    "system": item.system,
                    "code": item.code,
                    "display": item.display,
                    "source": item.source,
                }
                for item in request.candidates
            ],
        }
        document = self._transport.request(
            method="POST",
            url=f"{self._base_url}/v1/coding/rank",
            headers=self._headers(),
            body={"jsonapi": {"version": "1.1"}, "data": [{"type": "coding-ranking-request", "attributes": attributes}]},
        )
        allowed = {item.candidate_id: item for item in request.candidates}
        data = document.get("data", [])
        response_attributes = data[0].get("attributes", {}) if isinstance(data, list) and data and isinstance(data[0], dict) else {}
        ranking = response_attributes.get("ranking", []) if isinstance(response_attributes, dict) else []
        ranked: list[CodingSuggestion] = []
        seen: set[str] = set()
        for item in ranking:
            if not isinstance(item, dict):
                continue
            candidate_id = str(item.get("candidateId", "")).strip()
            candidate = allowed.get(candidate_id)
            if candidate is None or candidate_id in seen:
                continue
            seen.add(candidate_id)
            ranked.append(
                CodingSuggestion.from_candidate(
                    candidate,
                    recommendation_percent=float(item.get("recommendationPercent", 0.0) or 0.0),
                    evidence=str(item.get("evidence", "")),
                )
            )
        return ranked

    def submit(self, event: dict[str, Any]) -> None:
        proposal_id = str(event.get("proposalId", "")).strip()
        self._transport.request(
            method="POST",
            url=f"{self._base_url}/v1/coding/feedback",
            headers=self._headers(),
            body={
                "jsonapi": {"version": "1.1"},
                "data": [{
                    "type": "coding-review-feedback",
                    "id": proposal_id,
                    "attributes": dict(event),
                }],
            },
        )
