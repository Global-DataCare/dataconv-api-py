# TODO Data Space Artifacts (DataConv)

## Goal
Align DataConv transformations with canonical Gaia-X artifact models used by ICA and GW/UNID.

## Artifact Coverage

- Legal organization credential/profile
- Legal representative credential/profile
- Employee credential/profile
- Person subject profile
- Animal subject profile
- RelatedPerson profile with explicit role semantics

## DataConv Responsibilities

- Source-to-canonical mapping rules for each artifact family.
- Validation and normalization rules before delivery to GW/UNID.
- Explicit handling for role and relationship semantics.

## Schema and Mapping Work

- Versioned mapping specs per source format.
- Required/optional field matrix per artifact type.
- Deterministic error reporting for unmapped/invalid fields.

## Alignment Targets

- ICA schema/profile requirements.
- GW/UNID persistence and lookup expectations.
- Shared terminology and role taxonomy to avoid semantic drift.

## SDK Types (Next)

- Ensure generated/consumed models stay aligned with:
  - `dataspace-client-sdk-node`
  - Python SDK (`connector-sdk-py`)
- Add typed payload contracts for converted artifacts where missing.

## Test Plan

- Golden files for conversion outputs per artifact type.
- Contract tests against GW ingestion and ICA validation.
- Regression tests for namespace, sector, and role mismatches.
