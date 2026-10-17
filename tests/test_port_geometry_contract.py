import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from src.portwatch_os.geospatial.geometry import accuracy_report, to_local, to_three, validate_catalogue
from src.portwatch_os.geospatial.layers import GeospatialLayer

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_osm", ROOT / "scripts/port_geometry/build_osm.py")
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)


class TransformTests(unittest.TestCase):
    def test_origin_and_axes(self):
        self.assertEqual(to_local([72.95, 18.95], [72.95, 18.95]), (0, 0, 0))
        east = to_local([72.951, 18.95], [72.95, 18.95])
        north = to_local([72.95, 18.951], [72.95, 18.95])
        self.assertAlmostEqual(east[0], 105.3, delta=.1)
        self.assertAlmostEqual(north[1], 110.69, delta=.1)
        self.assertLess(abs(east[1]), .001)
        self.assertEqual(to_three((10, 20, 30)), (10, 30, -20))

    def test_known_equator_distance_and_vertical(self):
        self.assertAlmostEqual(to_local([.001, 0], [0, 0])[0], 111.3194908, places=5)
        self.assertAlmostEqual(to_local([0, 0, 12], [0, 0, 2])[2], 10, places=6)

    def test_bad_crs_and_coordinates(self):
        for p in ([181, 0], [0, 91], [float("nan"), 0], [True, 0], [0]):
            with self.assertRaises(ValueError): to_local(p, [0, 0])
        with self.assertRaises(ValueError): to_local([0, 0], [0, 0], "EPSG:3857")


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / "data/port_geometry/INNSA/osm-20261017-v1"
        self.catalogue = json.loads((self.path / "footprints.geojson").read_text())

    def test_retained_integrity_and_reproduction(self):
        manifest = json.loads((self.path / "manifest.json").read_text())
        raw = (self.path / manifest["original"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["originalSha256"])
        self.assertEqual(hashlib.sha256((self.path / "footprints.geojson").read_bytes()).hexdigest(), manifest["catalogueSha256"])
        c = self.catalogue
        rebuilt = importer.build(raw, c["portCode"], c["geometryVersion"], c["origin"], c["sources"][0]["firstAvailableAt"], c["sources"][0]["url"])
        self.assertEqual(rebuilt, c)
        self.assertGreater(len(validate_catalogue(c)["features"]), 100)
        self.assertEqual((ROOT / "india-portwatch-terminal/public/port-geometry/INNSA/osm-20261017-v1.geojson").read_bytes(), (self.path / "footprints.geojson").read_bytes())

    def test_unreviewed_mappings_and_missing_features_rejected(self):
        for mapping in ({"featureId": "missing", "operationalAssetId": None},
                        {"featureId": self.catalogue["features"][0]["id"], "operationalAssetId": "berth-1", "status": "proposed"}):
            c = copy.deepcopy(self.catalogue)
            c["operationalMappings"] = [mapping]
            with self.assertRaises(ValueError): validate_catalogue(c)

    def test_missing_source_duplicate_feature_and_bad_coordinates(self):
        for change in (lambda c: c["features"].append(c["features"][0]),
                       lambda c: c["features"][0]["properties"].update(sourceIds=["absent"]),
                       lambda c: c.update(horizontalCrs="EPSG:3857")):
            c = copy.deepcopy(self.catalogue)
            change(c)
            with self.assertRaises(ValueError): validate_catalogue(c)

    def test_unknowns_are_not_promoted(self):
        self.assertEqual(self.catalogue["operationalMappings"], [])
        for f in self.catalogue["features"]:
            self.assertIsNone(f["properties"]["heightM"])
            self.assertIsNone(f["properties"]["sourceDate"])
            self.assertEqual(f["properties"]["horizontalQuality"], "Unknown")

    def test_incomplete_ways_are_not_fabricated(self):
        raw = b'<osm><node id="1" lon="72.95" lat="18.95"/><way id="2"><nd ref="1"/><nd ref="9"/><tag k="man_made" v="pier"/></way></osm>'
        c = importer.build(raw, "INNSA", "test", [72.95,18.95], "2026-10-17", "fixture")
        self.assertEqual(c["features"], [])
        self.assertEqual(c["skipped"], [{"id": "2", "reason": "incomplete way"}])

    def test_accuracy_requires_independent_evidence(self):
        self.assertIsNone(accuracy_report([])["p95M"])
        with self.assertRaises(ValueError): accuracy_report([{"role": "fit", "referenceSourceId": "survey"}])
        rows = [{"role": "check", "referenceSourceId": "survey", "modelEN": [0, 0], "referenceEN": [3, 4]},
                {"role": "check", "referenceSourceId": "survey", "modelEN": [0, 0], "referenceEN": [0, 10]}]
        self.assertEqual(accuracy_report(rows)["medianM"], 7.5)
        self.assertEqual(accuracy_report(rows)["p95M"], 9.75)

    def test_layer_keeps_analytical_and_display_values_separate(self):
        layer = GeospatialLayer("sample", "INNSA", "vector", [72.9,18.9,73,19], "EPSG:4326")
        self.assertIsNone(layer.to_dict()["nativeResolutionM"])
        with self.assertRaises(ValueError):
            GeospatialLayer("sample", "INNSA", "raster", [72.9,18.9,73,19], "EPSG:4326", displayResource={"valueKind": "observed"}).to_dict()


if __name__ == "__main__": unittest.main()
