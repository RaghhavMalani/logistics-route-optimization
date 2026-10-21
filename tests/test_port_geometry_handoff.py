"""Exercise the deliverable outside the source checkout, including all API assets."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

from scripts.port_geometry.package_handoff import package


class HandoffTests(unittest.TestCase):
    def test_clean_extraction_serves_all_required_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "handoff.zip"
            result = package(archive)
            self.assertEqual(result["featureCount"], 3256)
            with self.assertRaises(FileExistsError):
                package(archive)
            extracted = root / "extracted"
            with ZipFile(archive) as bundle:
                bundle.extractall(extracted)
            checksums = json.loads((extracted / "SHA256SUMS.json").read_text())
            for name, digest in checksums.items():
                self.assertEqual(hashlib.sha256((extracted / name).read_bytes()).hexdigest(), digest)
            self.assertFalse((extracted / ".env").exists())
            code = '''
from fastapi.testclient import TestClient
from backend.geospatial_preview import app
client = TestClient(app)
root = "/api/public/port-geometry/INNSA"
manifest = client.get(root)
assert manifest.status_code == 200
assert len(client.get(manifest.json()["geometryUrl"]).json()["features"]) == 3256
catalogue = client.get(manifest.json()["layersUrl"])
assert catalogue.status_code == 200
for layer in catalogue.json()["layers"]:
    response = client.get(layer["displayResource"]["url"])
    assert response.status_code == 200
    assert response.content.startswith(b"\\x89PNG")
    validation = client.post(root + "/validate-layer", json=layer)
    assert validation.status_code == 200 and validation.json()["persisted"] is False
assert client.get("/api/port-twin/INNSA").status_code == 404
print("Clean extracted API smoke passed")
'''
            env = dict(os.environ)
            env.pop("PORTWATCH_GEOSPATIAL_LAYERS_FILE", None)
            # Preserve dependency directories but exclude the checkout from import search.
            env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path
                if p and "site-packages" in p or p and p.startswith("/private/tmp/port-geometry-python"))
            completed = subprocess.run([sys.executable, "-c", code], cwd=extracted,
                env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
