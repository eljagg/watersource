"""Upload validation: size, extension vs magic-byte MIME, optional ClamAV scan
(ToR §9 'file upload validation', 'malware scanning of uploaded files')."""
import hashlib
import socket
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

try:
    import magic  # python-magic
except ImportError:  # pragma: no cover
    magic = None


def sha256_of(fileobj) -> str:
    h = hashlib.sha256()
    for chunk in fileobj.chunks():
        h.update(chunk)
    fileobj.seek(0)
    return h.hexdigest()


def validate_upload(fileobj, allowed=None):
    allowed = allowed or settings.UPLOAD_ALLOWED_TYPES
    if fileobj.size > settings.UPLOAD_MAX_BYTES:
        raise ValidationError(f"File is larger than {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB.")
    ext = Path(fileobj.name).suffix.lower()
    detected = None
    if magic is not None:
        head = fileobj.read(4096)
        fileobj.seek(0)
        detected = magic.from_buffer(head, mime=True)
    if detected is not None:
        if detected not in allowed:
            raise ValidationError(f"File type '{detected}' is not permitted.")
        if ext not in allowed[detected]:
            raise ValidationError("File extension does not match its content.")
    else:  # pragma: no cover - libmagic missing
        if ext not in {e for exts in allowed.values() for e in exts}:
            raise ValidationError("File extension is not permitted.")
    return detected or "application/octet-stream"


def clamav_scan(fileobj) -> str:
    """Return 'clean', 'infected:<sig>' or 'skipped' (no scanner configured)."""
    host = settings.CLAMAV_HOST
    if not host:
        return "skipped"
    with socket.create_connection((host, settings.CLAMAV_PORT), timeout=30) as s:
        s.sendall(b"zINSTREAM\0")
        for chunk in fileobj.chunks():
            s.sendall(len(chunk).to_bytes(4, "big") + chunk)
        s.sendall(b"\0\0\0\0")
        reply = s.recv(4096).decode(errors="ignore").strip()
    fileobj.seek(0)
    if reply.endswith("OK"):
        return "clean"
    return "infected:" + reply
