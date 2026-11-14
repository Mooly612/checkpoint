import pytest
from checkpoint.core import safe_xml
from checkpoint.vendor.defusedxml.common import DefusedXmlException


@pytest.mark.parametrize('xml', [
    '<!DOCTYPE qgis [<!ENTITY x "expanded">]><qgis>&x;</qgis>',
    '<!DOCTYPE qgis [<!ENTITY x SYSTEM "file:///etc/passwd">]><qgis>&x;</qgis>',
])
def test_entities_rejected_before_parsing_or_canonicalization(xml):
    for operation in (safe_xml.fromstring, safe_xml.canonicalize):
        with pytest.raises(DefusedXmlException):
            operation(xml)


def test_qgis_doctype_without_entities_remains_supported():
    assert safe_xml.fromstring('<!DOCTYPE qgis PUBLIC "qgis" "http://example.invalid/qgis.dtd"><qgis/>').tag == 'qgis'
