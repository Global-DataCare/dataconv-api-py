# current-output

Muestras mínimas del contrato de salida vigente del adaptador.

Archivos:

- `composition-message.sample.json`
- `summary.sample.json`

Notas:

- Son extractos (`total: 1` para los mensajes) de una ejecución real en `--dry-run`.
- Se mantienen en el repo para documentación estable, sin depender de `artifacts/` (que está en `.gitignore`).
- `body.data[].resource` ahora usa `Patient` como recurso principal.
- Cada `Patient.contained[]` agrupa `Composition`, `DocumentReference` y `Encounter`.
- `Composition.section` y `Composition.type` van codificados con LOINC.
- `Composition.entry` usa referencias `urn:uuid:<uuid>`.
- En este ejemplo (`dataUse=secondary`) no se incluye `DocumentReference.text`.
