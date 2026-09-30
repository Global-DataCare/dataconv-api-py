# Codificación de vacunas de Elysa

El comando de enriquecimiento crea un libro derivado y nunca sobrescribe el
original. Añade en la fila 2 de todas las hojas estos nombres canónicos de flat
claims:

```text
Immunization.vaccine-code
Immunization.vaccine-code-display
Immunization.vaccine-code-text
```

El código es una lista CSV de valores `system|code`. El display internacional
y el texto en español son listas CSV correlacionadas en el mismo orden; el
escape CSV estándar conserva las comas internas de los displays oficiales. Las
cuatro primeras hojas, de animales, usan WHO ATCvet; las tres últimas, humanas,
usan WHO ATC. Es correcto que una hoja como la de odontología tenga las tres
columnas completamente vacías.

Este paso registra candidatos de terminología internacional, no códigos de
productos comerciales ni autorizaciones regionales. Un nombre de producto o
un texto explícito de administración puede permitir inferir ATC/ATCvet, pero
una formulación ambigua conserva varios candidatos o un grupo más amplio y
queda pendiente de revisión. No se convierten en Immunization los disolventes,
las recomendaciones, el simple estado vacunal ni filas ajenas a vacunas.

En hojas animales, el texto local de especie no se convierte directamente en
un TaxId. DataConv usa primero el idioma BCP 47 de `API-CONFIG` y después inglés,
buscando el valor completo y acortándolo progresivamente hasta tres caracteres
solo para recuperar candidatos del conjunto NCBI cerrado soportado por ATCvet.
El modelo clasifica los candidatos con el contexto de la fila. Sin modelo, solo
un candidato único encontrado con cuatro o más caracteres puede usarse como
contexto de enrutado para consultar ATCvet; nunca queda confirmado como dato
revisado. Una coincidencia de tres caracteres, ambigua o no soportada conserva
el texto para revisión y no provoca una petición ATCvet inválida. No se elimina
la última letra de todas las especies ni se compara texto libre por substring.

Ejecución con Python 3.11 y el extra de Excel instalado:

```bash
PYTHONPATH=src python scripts/enrich-elysa-immunizations.py \
  "/privado/original/2026-08-31- Elysa - tratameintos - API-CONFIG.xlsx" \
  "/privado/resultados/2026-08-31- Elysa - tratameintos - API-CONFIG - IMMUNIZATION-CODED.xlsx" \
  --evidence-dir "/privado/resultados/elysa-immunization-coding"
```

La carpeta de evidencias contiene un resumen legible y ficheros CSV y JSON con
el texto original, candidatos, displays, texto en español, especies NCBI
inferidas, confianza y filas de origen. Contienen texto clínico y deben quedar
fuera del repositorio público.
