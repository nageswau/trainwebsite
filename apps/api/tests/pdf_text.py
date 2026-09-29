"""ENH-015: the plain text of a reportlab PDF, for assertions. Standard library only -- no PDF library is a dependency.
Decodes every content stream (reportlab writes `/Filter [ /ASCII85Decode /FlateDecode ]`) and collects the strings shown
by `Tj`; enough for reportlab's own output with the built-in fonts, which is all the reports use."""

import base64
import binascii
import re
import zlib

_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)  # reportlab writes "...~>endstream" with no newline
_TEXT_OBJECT = re.compile(rb"BT(.*?)ET", re.S)
_SHOW = re.compile(rb"\(((?:\\.|[^\\)])*)\)\s*Tj")
_ESCAPE = re.compile(rb"\\([0-7]{1,3}|.)", re.S)  # a PDF string escape: octal code or an escaped character


def _decode(raw: bytes) -> bytes:
    body = raw.strip().removesuffix(b"~>")  # reportlab ends ASCII85 data with "~>" but omits the leading "<~"
    try:
        raw = base64.a85decode(body)
    except (ValueError, binascii.Error):
        return raw
    try:
        return zlib.decompress(raw)
    except zlib.error:
        return raw


def _unescaped(match: re.Match) -> bytes:
    escaped = match.group(1)
    return bytes([int(escaped, 8)]) if escaped[:1].isdigit() else escaped


def _unescape(text: bytes) -> str:
    return _ESCAPE.sub(_unescaped, text).decode("cp1252", errors="replace")


def pdf_text(data: bytes) -> str:
    """One output line per text object (reportlab draws a paragraph line as one BT..ET, split into several `Tj` runs)."""
    out = []
    for raw in _STREAM.findall(data):
        for block in _TEXT_OBJECT.findall(_decode(raw)):
            out.append("".join(_unescape(text) for text in _SHOW.findall(block)))
    return "\n".join(out)
