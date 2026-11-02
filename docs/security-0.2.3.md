# XML security fix, 0.2.3

The 0.2.2 upload report contained eight Bandit XML findings. Secrets Detection
reported zero findings. Plugin XML parsing now uses bundled defusedxml 0.7.1
(pure Python; PSF license included). Qt parsing is preceded by safe validation.
Entities and external references are rejected; QGIS DOCTYPEs remain supported.
Canonicalization reparses only validated, reserialized entity-free XML.

Focused B405 annotations cover the stdlib serializer import and primitives inside
defusedxml's protected parser, not plugin parse calls. No scanner-wide exclusions
are used. Vendored files come from PyPI 0.7.1; unused global monkey-patching was
removed, an internal identity assert became an exception, and safe imports were
annotated for Bandit. No additional user installation is required.

Tests exercise malicious internal/external entities and ordinary QGIS XML.
Approval still requires a fresh repository scan of the uploaded version.
