# Future authorized camera boundary

No actual camera, pose, footage or coverage polygon is claimed by this branch.
Future camera observations should use this provider-neutral metadata shape:

```json
{
  "schemaVersion": "port-camera-view/1",
  "viewId": "PROVIDER_ASSIGNED_ID",
  "portCode": "INNSA",
  "assetIds": [],
  "horizontalCrs": "EPSG:4326",
  "pose": {
    "longitude": null,
    "latitude": null,
    "elevationM": null,
    "verticalDatum": null,
    "headingDegreesClockwiseFromNorth": null,
    "pitchDegrees": null,
    "rollDegrees": null
  },
  "coveragePolygon": null,
  "coverageReview": {
    "status": "unreviewed",
    "reviewedBy": null,
    "reviewedAt": null,
    "sourceReceiptId": null
  },
  "authorizationReference": null,
  "observedAt": null,
  "firstAvailableAt": null
}
```

`assetIds` must refer to geographic IDs from the geometry API, not inferred
simulator indices. A coverage polygon is EPSG:4326 GeoJSON and must carry a
reviewed footprint, source receipt and authorization before supporting an
operational observation. Unknown pose fields stay null. Credentials and footage
access are backend-controlled. A camera image is not a reliable position/depth
observation without calibration, coverage, time and review. This is a future
contract seam, not an implemented camera ingest endpoint or CV model.
