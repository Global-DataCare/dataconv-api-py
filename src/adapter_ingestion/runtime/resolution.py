# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from dataclasses import replace

from .models import ConfigKey


def resolution_candidates(selector: ConfigKey) -> list[ConfigKey]:
    """
    Resolution order (most specific -> most generic):
      1) version exact + country + facility
      2) version exact + country
      3) version exact + facility
      4) version exact (org level)
      5) version default + country + facility
      6) version default + country
      7) version default + facility
      8) version default (org level)
    """
    normalized = selector.normalized()
    version_variants = [normalized.manufacturer_version]
    if normalized.manufacturer_version:
        version_variants.append("")

    candidates: list[ConfigKey] = []
    seen: set[str] = set()
    pairs = [
        (normalized.country, normalized.facility_id),
        (normalized.country, ""),
        ("", normalized.facility_id),
        ("", ""),
    ]

    for version in version_variants:
        for country, facility_id in pairs:
            candidate = replace(
                normalized,
                manufacturer_version=version,
                country=country,
                facility_id=facility_id,
            )
            token = candidate.as_token()
            if token not in seen:
                seen.add(token)
                candidates.append(candidate)
    return candidates

