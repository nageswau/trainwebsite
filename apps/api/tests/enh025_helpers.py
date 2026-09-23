"""ENH-025 byte builders: minimal, structurally valid JPEG/PNG files with and without metadata."""

import struct
import zlib


def _segment(marker: int, payload: bytes) -> bytes:
    return bytes([0xFF, marker]) + struct.pack(">H", len(payload) + 2) + payload


def jpeg_bytes(with_gps: bool = True) -> bytes:
    parts = [b"\xff\xd8", _segment(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")]
    if with_gps:
        parts.append(_segment(0xE1, b"Exif\x00\x00GPSLatitude=18.52;GPSLongitude=73.85"))
        parts.append(_segment(0xFE, b"comment: home address"))
    parts.append(_segment(0xE2, b"ICC_PROFILE\x00\x01\x01profile"))
    parts.append(_segment(0xDB, b"\x00" + bytes(64)))
    parts.append(_segment(0xDA, b"\x01\x01\x00\x00\x3f\x00") + b"\x12\x34\x56\xff\x00\x78" + b"\xff\xd9")
    return b"".join(parts)


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(with_text: bool = True) -> bytes:
    parts = [b"\x89PNG\r\n\x1a\n", _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))]
    if with_text:
        parts += [_chunk(b"tEXt", b"Location\x00Pune"), _chunk(b"eXIf", b"GPS"), _chunk(b"tIME", bytes(7))]
    parts += [_chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")), _chunk(b"IEND", b"")]
    return b"".join(parts)
