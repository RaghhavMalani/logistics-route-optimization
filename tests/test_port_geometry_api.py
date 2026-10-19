import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend.geospatial_preview import app
from src.portwatch_os.geospatial.catalogue_service import geometry, layers, port_directory
from src.portwatch_os.geospatial.catalogue_service import is_public_geometry_request


class PublicGeographicApiTests(unittest.TestCase):
    def test_authority_release_rebuilds_from_retained_sources_offline(self):
        from scripts.port_geometry.build_authority_pilot import build
        release=port_directory("INNSA")
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/"release"; public=Path(folder)/"public"
            build(release/"originals",release/"reference",output,public)
            self.assertEqual((output/"footprints.geojson").read_bytes(),(release/"footprints.geojson").read_bytes())
            self.assertEqual((output/"layers.json").read_bytes(),(release/"layers.json").read_bytes())
            self.assertEqual((public/"reference.png").read_bytes(),(release/"reference/reference.png").read_bytes())

    def test_only_static_geometry_and_dry_run_validation_are_public(self):
        for method,path in (("GET","/api/public/port-geometry/INNSA"),("GET","/api/public/port-geometry/INNSA/geometry"),("GET","/api/public/port-geometry/INNSA/layers"),("GET","/api/public/port-geometry/INNSA/reference-image"),("POST","/api/public/port-geometry/INNSA/validate-layer")):
            self.assertTrue(is_public_geometry_request(method,path))
        for method,path in (("POST","/api/public/port-geometry/INNSA/layers"),("DELETE","/api/public/port-geometry/INNSA"),("GET","/api/port-twin/INNSA"),("POST","/api/auth/login"),("GET","/api/public/port-geometry/INNSA/../../auth/session"),("GET","/api/public/port-geometry/INNSA/geometry/private")):
            self.assertFalse(is_public_geometry_request(method,path))

    def setUp(self):
        self.client=TestClient(app)
        self.layer=layers("INNSA")["layers"][0]

    def test_handshake_geometry_layer_and_display_routes(self):
        root="/api/public/port-geometry/INNSA"
        r=self.client.get(root)
        self.assertEqual(r.status_code,200)
        self.assertEqual(r.json()["deliveryMode"],"pull-reviewed-catalogue")
        c=self.client.get(r.json()["geometryUrl"]).json()
        self.assertEqual(c["portCode"],"INNSA")
        self.assertEqual(len([f for f in c["features"] if f["id"].startswith("jnpa-berth-")]),13)
        self.assertNotIn("calls",c)
        self.assertNotIn("accessToken",c)
        image=self.client.get(self.layer["displayResource"]["url"])
        self.assertEqual(image.status_code,200)
        self.assertTrue(image.content.startswith(b"\x89PNG"))

    def test_validation_does_not_persist(self):
        directory=port_directory("INNSA")
        before=(directory/"layers.json").read_bytes()
        response=self.client.post("/api/public/port-geometry/INNSA/validate-layer",json=self.layer)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()["persisted"])
        self.assertEqual(before,(directory/"layers.json").read_bytes())

    def test_invalid_crs_assets_dates_urls_resolution_and_values(self):
        changes=[{"horizontalCrs":"EPSG:3857"},{"portCode":"INMAA"},{"assetIds":["nonexistent"]},
                 {"nativeResolutionM":-1},{"sourceHashes":["not-a-hash"]},
                 {"acquisitionFrom":"2026-01-01T20:00:00Z","acquisitionThrough":"2026-01-01T10:00:00Z"},
                 {"displayResource":{"url":"file:///etc/passwd","valueKind":"display"}},
                 {"displayResource":{"url":"https://user:password@example.org/image.png","valueKind":"display"}},
                 {"displayResource":{"url":"/image.png","valueKind":"observed"}},
                 {"displayResource":[]}, {"kind":"bathymetry-guessed"}]
        for change in changes:
            with self.subTest(change=change):
                candidate=copy.deepcopy(self.layer); candidate.update(change)
                response=self.client.post("/api/public/port-geometry/INNSA/validate-layer",json=candidate)
                self.assertEqual(response.status_code,422,response.text)

    def test_unknown_port_and_bad_config_do_not_fabricate_data(self):
        self.assertEqual(self.client.get("/api/public/port-geometry/INMAA").status_code,404)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"layers.json"; path.write_text('{"layers": []}')
            with patch.dict(os.environ,{"PORTWATCH_GEOSPATIAL_LAYERS_FILE":str(path)}):
                self.assertEqual(self.client.get("/api/public/port-geometry/INNSA/layers").status_code,503)

    def test_reviewed_unmapped_dispositions_are_not_identity_claims(self):
        c=geometry("INNSA")
        self.assertEqual(len(c["operationalMappings"]),13)
        for mapping in c["operationalMappings"]:
            self.assertIsNone(mapping["operationalAssetId"])
            self.assertEqual(mapping["status"],"reviewed-unmapped")
            self.assertTrue(mapping["reason"])


if __name__=="__main__": unittest.main()
