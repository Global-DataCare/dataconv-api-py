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

CREATE_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create"
CREATE_RESPONSE_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/{software-id}/config/_create-response"
UPLOAD_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload"
UPLOAD_RESPONSE_PATH = (
    "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_upload-response"
)
PATCH_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_patch"
BATCH_PATH = "/{tenant-id}/cds-{jurisdiction}/v1/{sector}/digitaltwin/{software-id}/{resource-type}/_batch"
SEARCH_PATH = "/host/cds-{jurisdiction}/v1/{sector}/{tenant-id}/org.hl7.fhir.api/{resource-type}/_search"
