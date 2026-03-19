# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .tabular_xlsx import TabularXlsxAdapter


class WakymaAdapter(TabularXlsxAdapter):
    name = "wakyma"
    source_namespace = "wakyma"
    default_header_row_index = 2
    # Wakyma species can be embedded in "Mascota" text; unmatched values are ignored.
    species_fallback_to_source = False
    default_field_map = {
        "section": "",
        "family": "Tipo",
        "subfamily": "Tipo",
        "concept": "Motivo",
        "subjectId": "ID Interno Paciente",
        "owner": "",
        "ownerId": "",
        "species": "Mascota",
        "breed": "",
        "genderStatus": "",
        "sourceId": "",
        "date": "Fecha",
        "time": "Hora",
    }
    default_field_defaults = {
        "section": "clinica",
    }
    default_species_contains = [
        {"contains": "Perro", "value": "Perro"},
        {"contains": "Gato", "value": "Gato"},
        {"contains": "Conejo", "value": "Conejo"},
        {"contains": "Cobaya", "value": "Cobaya"},
        {"contains": "Ave", "value": "Ave"},
    ]
    default_loinc_overrides = {
        "clinica:vacunacion": "11369-6",
        "clinica:consulta": "34109-9",
        "clinica:revision": "34109-9",
        "clinica:*": "11503-0",
    }
