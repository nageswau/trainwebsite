"""ENH-025 -- identify JPEG/PNG by magic bytes and strip metadata without decoding pixels (no image library;
docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md §5). Location data in phone photos
(EXIF GPS) must never be stored for a minor."""

JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Dropped: APP1 (EXIF/XMP, incl. GPS), APP3-APP13 (incl. APP13 Photoshop/IPTC), APP15, COM. Kept: APP0 (JFIF),
# APP2 (ICC colour profile) and APP14 (Adobe colour transform) -- they carry no personal data and dropping
# them can mis-colour the image.
_JPEG_DROP = {0xE1, *range(0xE3, 0xEE), 0xEF, 0xFE}
_PNG_DROP = {b"tEXt", b"iTXt", b"zTXt", b"eXIf", b"tIME"}


class InvalidImage(ValueError):
    pass


def detect_image_type(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8\xff"):
        return JPEG
    if data.startswith(_PNG_SIGNATURE):
        return PNG
    return None


_JPEG_SOF = {*range(0xC0, 0xC4), *range(0xC5, 0xC8), *range(0xC9, 0xCC), *range(0xCD, 0xD0)}


def image_size(data: bytes, content_type: str) -> tuple[int, int] | None:
    """nehn-035 (DEC-SCOPE-328 L2): (width, height) read from a PNG, JPEG or WebP header without decoding pixels; None when unreadable."""
    if content_type == PNG:
        if len(data) < 24 or data[12:16] != b"IHDR":
            return None
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if content_type == JPEG:
        i = 2
        while i + 9 <= len(data) and data[i] == 0xFF:
            marker = data[i + 1]
            if marker in _JPEG_SOF:
                return int.from_bytes(data[i + 7 : i + 9], "big"), int.from_bytes(data[i + 5 : i + 7], "big")
            if marker in (0xD9, 0xDA):
                return None
            i += 2 + int.from_bytes(data[i + 2 : i + 4], "big")
        return None
    if content_type == WEBP and len(data) >= 30:
        kind = data[12:16]
        if kind == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        if kind == b"VP8 ":
            return int.from_bytes(data[26:28], "little") & 0x3FFF, int.from_bytes(data[28:30], "little") & 0x3FFF
        if kind == b"VP8L":
            bits = int.from_bytes(data[21:25], "little")
            return 1 + (bits & 0x3FFF), 1 + ((bits >> 14) & 0x3FFF)
    return None


def strip_metadata(data: bytes, content_type: str) -> bytes:
    if content_type == JPEG:
        return _strip_jpeg(data)
    if content_type == PNG:
        return _strip_png(data)
    raise InvalidImage("unsupported image type")


def _strip_jpeg(data: bytes) -> bytes:
    out = bytearray(b"\xff\xd8")
    i, n = 2, len(data)
    while i < n:
        if data[i] != 0xFF:
            raise InvalidImage("expected a JPEG marker")
        while i < n and data[i] == 0xFF:
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        if marker == 0xD9:
            return bytes(out + b"\xff\xd9")
        if marker == 0xDA:
            # Entropy-coded scan data runs to the last end-of-image marker; anything after it (trailers,
            # appended documents) is dropped.
            end = data.rfind(b"\xff\xd9", i)
            if end == -1:
                raise InvalidImage("JPEG has no end-of-image marker")
            return bytes(out + b"\xff\xda" + data[i : end + 2])
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += bytes((0xFF, marker))
            continue
        if i + 2 > n:
            break
        length = int.from_bytes(data[i : i + 2], "big")
        if length < 2 or i + length > n:
            raise InvalidImage("JPEG segment runs past the end of the file")
        if marker not in _JPEG_DROP:
            out += bytes((0xFF, marker)) + data[i : i + length]
        i += length
    raise InvalidImage("JPEG is truncated")


def _strip_png(data: bytes) -> bytes:
    if not data.startswith(_PNG_SIGNATURE):
        raise InvalidImage("not a PNG")
    out = bytearray(_PNG_SIGNATURE)
    i, n = len(_PNG_SIGNATURE), len(data)
    while i + 8 <= n:
        length = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        end = i + 12 + length
        if end > n:
            raise InvalidImage("PNG chunk runs past the end of the file")
        if kind not in _PNG_DROP:
            out += data[i:end]
        i = end
        if kind == b"IEND":
            return bytes(out)
    raise InvalidImage("PNG is truncated")
