# Copyright Conéctate Soluciones y Aplicaciones SL
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from .tabular_xlsx import TabularXlsxAdapter


class QvetAdapter(TabularXlsxAdapter):
    name = "qvet"
    source_namespace = "qvet"
    default_header_row_index = 1
    species_fallback_to_source = True
    default_field_map = {
        "section": "SECCION",
        "family": "FAMILIA",
        "subfamily": "SUBFAMILIA",
        "concept": "CONCEPTO",
        "subject_id": "HISTORIA_ID",
        "owner": "",
        "ownerId": "",
        "species": "ESPECIE",
        "breed": "",
        "genderStatus": "",
        "sourceId": "IDARTICULO",
        "date": "FECHA",
        "time": "HORA",
    }
    default_field_defaults = {}
    default_species_contains = []
    default_loinc_overrides = {
        "clinica:vacunas": "11369-6",
        "clinica:laboratorio": "30954-2",
        "clinica:consultas": "34109-9",
        "clinica:cirugia": "11504-8",
        "clinica:diagnostico por imagen propio": "18726-0",
        "clinica:diagnostico por imagen externo": "18726-0",
        "clinica:medicamentos": "10160-0",
        "clinica:varios": "11503-0",
    }
