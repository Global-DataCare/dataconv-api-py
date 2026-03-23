# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

PUBLIC_PATH_PARAMS = {
    "tenant_id": "tenant-id",
    "manufacturer": "software-id",
    "software_id": "software-id",
    "resource_type": "resource-type",
    "sector": "sector",
    "job_id": "job-id",
}

CREATE_PATH = "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create"
CREATE_RESPONSE_PATH = "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create-response"
UPLOAD_PATH = "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{software-id}/{resource-type}/_upload"
UPLOAD_RESPONSE_PATH = (
    "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{software-id}/{resource-type}/_upload-response"
)
PATCH_PATH = "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{software-id}/{resource-type}/_patch"
BATCH_PATH = "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{software-id}/{resource-type}/_batch"
SEARCH_PATH = "/publisher/cds-{jurisdiction}/v1/{sector}/{tenant-id}/dataset/{resource-type}/_search"
EXCHANGE_PATH = "/exchange"
OAUTH_TOKEN_PATH = "/oauth/token"
API_KEY_CREATE_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_create"
API_KEY_DISABLE_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_disable"
API_KEY_REMOVE_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/api-key/org.schema/action/_remove"

LEGACY_CREATE_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create"
LEGACY_CREATE_RESPONSE_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create-response"
LEGACY_UPLOAD_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload"
LEGACY_UPLOAD_RESPONSE_PATH = (
    "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload-response"
)
LEGACY_PATCH_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_patch"
LEGACY_BATCH_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_batch"
LEGACY_SEARCH_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/org.hl7.fhir.api/{resource-type}/_search"

LEGACY_TO_CANONICAL_PATHS = {
    LEGACY_CREATE_PATH: CREATE_PATH,
    LEGACY_CREATE_RESPONSE_PATH: CREATE_RESPONSE_PATH,
    LEGACY_UPLOAD_PATH: UPLOAD_PATH,
    LEGACY_UPLOAD_RESPONSE_PATH: UPLOAD_RESPONSE_PATH,
    LEGACY_PATCH_PATH: PATCH_PATH,
    LEGACY_BATCH_PATH: BATCH_PATH,
    LEGACY_SEARCH_PATH: SEARCH_PATH,
}
