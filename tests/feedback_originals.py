"""Hash-checkable synthetic originals for semantic source-feedback regressions."""
import hashlib

NEWS_BYTES = b"SYNTHETIC source-report original; semantic test fixture only."
AUTHORITY_BYTES = b"SYNTHETIC authority evidence original; semantic test fixture only."
NEWS_ORIGINAL = hashlib.sha256(NEWS_BYTES).hexdigest()
AUTHORITY_ORIGINAL = hashlib.sha256(AUTHORITY_BYTES).hexdigest()


def retain_test_originals(root):
    archive = root / "shared_feedback"
    archive.mkdir(exist_ok=True)
    for raw in (NEWS_BYTES, AUTHORITY_BYTES):
        (archive / (hashlib.sha256(raw).hexdigest() + ".response")).write_bytes(raw)
