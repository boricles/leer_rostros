"""Tests for upload validation (file type and size limits)."""

import pytest

from app.main import MAX_UPLOAD_BYTES, _validate_image_data


class TestValidateImageData:
    """Tests for _validate_image_data."""

    def test_valid_jpeg(self):
        data = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        _validate_image_data(data)  # should not raise

    def test_valid_png(self):
        data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        _validate_image_data(data)  # should not raise

    def test_valid_webp(self):
        data = b"RIFF" + b"\x00" * 100
        _validate_image_data(data)  # should not raise

    def test_rejects_exe(self):
        data = b"MZ" + b"\x00" * 100
        with pytest.raises(ValueError, match="Formato de imagen no soportado"):
            _validate_image_data(data)

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Formato de imagen no soportado"):
            _validate_image_data(b"")

    def test_rejects_oversized(self):
        data = b"\xff\xd8\xff\xe0" + b"\x00" * MAX_UPLOAD_BYTES
        with pytest.raises(ValueError, match="excede el límite"):
            _validate_image_data(data)

    def test_accepts_at_limit(self):
        data = b"\xff\xd8\xff\xe0" + b"\x00" * (MAX_UPLOAD_BYTES - 4)
        _validate_image_data(data)  # should not raise
