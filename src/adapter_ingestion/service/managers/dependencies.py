# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...runtime import BlobStore, ISearchRepository, IVaultRepository, PreconversionControlPlane
from ..settings import ServiceSettings


@dataclass(frozen=True)
class ApiManagerDependencies:
    settings: ServiceSettings
    control_plane: PreconversionControlPlane
    blob_store: BlobStore
    vault_repo: IVaultRepository
    search_repo: ISearchRepository
    config_create_responses: dict[str, dict[str, Any]]
