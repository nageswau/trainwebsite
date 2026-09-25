"""ENH-025 -- identify JPEG/PNG by magic bytes and strip metadata without decoding pixels (no image library;
docs/superpowers/specs/2026-09-23-enh-025-student-master-fields-design.md §5). Location data in phone photos
(EXIF GPS) must never be stored for a minor."""

JPEG = "image/jpeg"
PNG = "image/png"
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
