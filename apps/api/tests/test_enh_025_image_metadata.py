"""ENH-025 -- photo type detection and metadata stripping (spec §5 privacy row), storage read/delete."""

import pytest

from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import StorageService
from enh025_helpers import jpeg_bytes, png_bytes


def test_detects_by_magic_bytes_only():
    assert detect_image_type(jpeg_bytes()) == "image/jpeg"
    assert detect_image_type(png_bytes()) == "image/png"
    assert detect_image_type(b"<svg xmlns='http://www.w3.org/2000/svg'/>") is None
    assert detect_image_type(b"<html><script>alert(1)</script>") is None
    assert detect_image_type(b"") is None


def test_jpeg_exif_and_comments_removed_icc_kept():
    out = strip_metadata(jpeg_bytes(with_gps=True), "image/jpeg")
    assert b"GPSLatitude" not in out and b"home address" not in out
    assert b"ICC_PROFILE" in out and b"JFIF" in out
    assert out.startswith(b"\xff\xd8") and out.endswith(b"\xff\xd9")
    assert out == jpeg_bytes(with_gps=False)


def test_jpeg_trailing_bytes_after_eoi_dropped():
    out = strip_metadata(jpeg_bytes(with_gps=False) + b"<html>trailer</html>", "image/jpeg")
    assert b"trailer" not in out and out.endswith(b"\xff\xd9")


def test_png_text_exif_time_chunks_removed():
    out = strip_metadata(png_bytes(with_text=True), "image/png")
    assert b"tEXt" not in out and b"eXIf" not in out and b"tIME" not in out and b"Pune" not in out
    assert out == png_bytes(with_text=False)


@pytest.mark.parametrize(("data", "kind"), [(jpeg_bytes()[:40], "image/jpeg"), (png_bytes()[:30], "image/png"), (b"\xff\xd8\xff\xe0\x00", "image/jpeg")])
def test_truncated_or_malformed_files_raise(data, kind):
    with pytest.raises(InvalidImage):
        strip_metadata(data, kind)


def test_storage_read_delete_round_trip_and_root_guard(tmp_path, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "aws_s3_bucket", "")
    monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
    store = StorageService()
    store.write_bytes("school-student-photos/abc", b"data", "image/png")
    assert store.read_bytes("school-student-photos/abc") == b"data"
    store.delete("school-student-photos/abc")
    store.delete("school-student-photos/abc")  # idempotent
    with pytest.raises(FileNotFoundError):
        store.read_bytes("school-student-photos/abc")
    with pytest.raises(ValueError):
        store.delete("../outside")
    with pytest.raises(ValueError):
        store.delete("")  # the storage root itself is never a delete target
