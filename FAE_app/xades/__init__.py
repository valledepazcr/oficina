import xmlsig

from cryptography.x509 import oid
from cryptography.x509.name import _NAMEOID_TO_NAME, _escape_dn_value

from lxml import etree
__all__ = ['get_reversed_rdns_name']

# This file should be imported after xmlsig or byitself if only XadesContext is used.

def get_reversed_rdns_name(rdns):
    """
    Gets the rdns String name, but in the right order. xmlsig original function produces a reversed order
    :param rdns: RDNS object
    :type rdns: cryptography.x509.RelativeDistinguishedName
    :return: RDNS name
    """
    data = []
    XMLSIG_NAMEOID_TO_NAME = _NAMEOID_TO_NAME.copy()
    XMLSIG_NAMEOID_TO_NAME[oid.NameOID.SERIAL_NUMBER] = "SERIALNUMBER"
    for dn in reversed(rdns):
        dn_data = []
        for attribute in dn._attributes:
            key = XMLSIG_NAMEOID_TO_NAME.get(
                attribute.oid, "OID.%s" % attribute.oid.dotted_string
            )
            dn_data.insert(0, "{}={}".format(key, _escape_dn_value(attribute.value)))
        data.insert(0, "+".join(dn_data))
    return ", ".join(data)


def b64_print(s):
    return s


# Monkey patching xmlsig functions to remove unecesary tail and body newlines
xmlsig.signature_context.b64_print = b64_print
xmlsig.algorithms.rsa.b64_print = b64_print
