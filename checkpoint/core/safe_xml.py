"""Entity-safe XML parsing shared by history, preflight and previews."""
# Only reserialized, entity-free trees reach the stdlib canonicalizer.
from xml.etree.ElementTree import canonicalize as _canonicalize  # nosec B405

from ..vendor.defusedxml.ElementTree import fromstring, tostring, ParseError


def canonicalize(xml):
    # Validate before the stdlib serializer reparses: entities and external
    # references are rejected by defusedxml, including embedded callout symbols.
    return _canonicalize(tostring(fromstring(xml), encoding="unicode"))
