# Model manifests

This directory contains logical model manifests such as face, plate, OCR,
speech, and PII metadata. Issue #14 owns the manifest schema, bootstrap,
checksum validation, and artifact resolver.

Every manifest is a JSON object with these fields. `type` defaults to `file` for
legacy manifests; use `archive` for a model pack that must be extracted before
loading:

```json
{
  "model_id": "plate-detector",
  "version": "v1",
  "type": "file",
  "filename": "plate-detector.pt",
  "source": {
    "url": "https://public.example/plate-detector.pt",
    "sha256": "64 lowercase hexadecimal characters"
  },
  "license": "upstream license identifier",
  "runtime": {
    "format": "ultralytics"
  }
}
```

An InsightFace pack uses the same handoff with an archive and runtime metadata:

```json
{
  "model_id": "face-buffalo-l",
  "version": "v1",
  "type": "archive",
  "filename": "buffalo_l.zip",
  "source": {
    "url": "https://public.example/buffalo_l.zip",
    "sha256": "64 lowercase hexadecimal characters"
  },
  "license": "upstream license identifier",
  "runtime": {
    "format": "insightface-pack",
    "model_name": "buffalo_l",
    "provider": "CPUExecutionProvider"
  }
}
```

The pack must contain the InsightFace layout expected by the adapter, such as
`models/buffalo_l/det_10g.onnx`. The resolver stores the verified archive under
`.cache/models/<model_id>/<version>/` and the verified extraction under its
`extracted/` child directory. `fetch` prints the file path for a file artifact or
the extraction directory for an archive artifact.

The local `plate-detector.json` manifest is an exception to the public-URL
example: it points to the developer-provided, ignored
`models/manifests/plate_detector.pt` file so the local plate-only demo can run.
Do not commit that weight or any other downloaded weights or provider
credentials here. Replace the local manifest source and license metadata with
the approved ML handoff before distribution.
