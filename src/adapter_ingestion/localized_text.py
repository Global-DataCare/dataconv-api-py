"""Reversible multilingual string encoding for claims-first FHIR text values."""

# Copyright ConnectHealth.info (Connecting Solution & Applications Ltd.)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import csv
from io import StringIO
import re
from typing import Iterable


_BCP47 = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


def _language(value: str) -> str:
    token = str(value or "").strip()
    if not _BCP47.fullmatch(token):
        raise ValueError("localized_text_language_invalid")
    return token


def encode_localized_text(
    values: Iterable[tuple[str, str]],
    *,
    base_language: str,
) -> str:
    """Use plain base-language text once; otherwise emit CSV `lang|text` values."""
    base = _language(base_language)
    normalized: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_language, raw_text in values:
        language = _language(raw_language)
        text = str(raw_text or "").strip()
        if not text:
            raise ValueError("localized_text_value_required")
        folded = language.casefold()
        if folded in seen:
            raise ValueError("localized_text_language_duplicate")
        seen.add(folded)
        normalized.append((language, text))
    if not normalized:
        return ""
    if len(normalized) == 1 and normalized[0][0].casefold() == base.casefold():
        return normalized[0][1]
    output = StringIO()
    csv.writer(output, lineterminator="").writerow(
        f"{language}|{text}" for language, text in normalized
    )
    return output.getvalue()


def decode_localized_text(value: str, *, base_language: str) -> tuple[tuple[str, str], ...]:
    """Decode tagged CSV, treating every non-tagged legacy value as base-language text."""
    base = _language(base_language)
    text = str(value or "")
    if not text:
        return ()
    items = next(csv.reader(StringIO(text)))
    decoded: list[tuple[str, str]] = []
    for item in items:
        language, separator, content = item.partition("|")
        if not separator or not _BCP47.fullmatch(language.strip()) or not content.strip():
            return ((base, text),)
        decoded.append((language.strip(), content.strip()))
    if len({language.casefold() for language, _ in decoded}) != len(decoded):
        raise ValueError("localized_text_language_duplicate")
    return tuple(decoded)
