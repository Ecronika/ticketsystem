"""
Tests for backup security — Zip Slip protection.

Verifies that BackupService.restore_backup() rejects ZIP archives that
contain path-traversal entries (../../etc/passwd etc.).
"""
import io
import os
import zipfile

import pytest

from services import BackupService


def _make_zip_with_traversal() -> bytes:
    """Return bytes of a ZIP file containing a Zip Slip path entry."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        # Safe entry
        zf.writestr('werkzeug.db', b'SQLite data')
        # Malicious path-traversal entry
        zf.writestr('../../../tmp/evil.txt', b'pwned')
    return buf.getvalue()


def test_zip_slip_rejected(test_app, tmp_path):
    """BackupService must reject ZIP files containing path-traversal entries."""
    malicious_zip = _make_zip_with_traversal()

    with test_app.app_context():
        # Simulate writing the ZIP to a temp file as restore_backup() expects
        zip_path = tmp_path / 'evil_backup.zip'
        zip_path.write_bytes(malicious_zip)

        # The function should either raise an exception or return an error dict
        try:
            result = BackupService.restore_backup(str(zip_path))
            # If it returns a result, it must indicate failure
            assert not result.get('success', True), (
                "restore_backup() should reject a Zip Slip archive")
        except (ValueError, PermissionError, zipfile.BadZipFile) as exc:
            # Raising an exception is also an acceptable rejection
            pass  # pylint: disable=broad-exception-caught
        else:
            # Confirm the traversal target was NOT written
            traversal_target = '/tmp/evil.txt'
            assert not os.path.exists(traversal_target), (
                "Zip Slip: traversal file was written to the filesystem!")
