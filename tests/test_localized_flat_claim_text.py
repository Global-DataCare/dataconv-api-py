# Flow contract: preserve one source text plainly and encode several BCP 47 language variants as reversible CSV flat-claim values.
# Copyright ConnectHealth.info (Connecting Solution & Applications Ltd.)
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from adapter_ingestion.localized_text import decode_localized_text, encode_localized_text


def test_single_base_language_text_stays_plain() -> None:
    value = encode_localized_text([("ca-ES", "tractament original")], base_language="ca-ES")

    assert value == "tractament original"
    assert decode_localized_text(value, base_language="ca-ES") == (("ca-ES", "tractament original"),)


def test_multiple_languages_round_trip_commas_quotes_and_newlines() -> None:
    values = (
        ("ca-ES", "Trusopt, una gota\nPreforte"),
        ("es-ES", 'Trusopt, "una gota"\nPreforte'),
    )

    encoded = encode_localized_text(values, base_language="ca-ES")

    assert decode_localized_text(encoded, base_language="ca-ES") == values
    assert encoded.startswith('"ca-ES|')


def test_multiple_languages_reject_invalid_or_duplicate_language_tags() -> None:
    with pytest.raises(ValueError, match="localized_text_language_invalid"):
        encode_localized_text([("es_ES", "texto")], base_language="es-ES")
    with pytest.raises(ValueError, match="localized_text_language_duplicate"):
        encode_localized_text(
            [("es-ES", "primero"), ("es-ES", "segundo")],
            base_language="es-ES",
        )
