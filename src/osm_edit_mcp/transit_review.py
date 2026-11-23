"""GeoJSON for reviewing road choices at specific bus survey points in iD."""

from typing import Any

from .place_features import ATTRIBUTION


def snap_review_geojson(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    features = []
    for review in reviews:
        index = review["point_index"]
        point = review["input_point"]
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "feature": "survey_point",
                    "point_index": index,
                    "name": f"Survey point {index}",
                    "marker-color": "#111827",
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [point["lon"], point["lat"]],
                },
            }
        )
        for candidate in review["candidates"]:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "feature": "road_candidate",
                        "point_index": index,
                        "way_id": candidate["way_id"],
                        "segment_index": candidate["segment_index"],
                        **(candidate["choice"] or {}),
                        "name": candidate["name"] or f"OSM way {candidate['way_id']}",
                        "selected": candidate["selected"],
                        "distance_m": candidate["distance_m"],
                        "allowed_directions": ", ".join(
                            candidate["allowed_directions"]
                        ),
                        "stroke": "#2563eb" if candidate["selected"] else "#d97706",
                    },
                    "geometry": candidate["segment_geometry"],
                }
            )
    return {
        "type": "FeatureCollection",
        "attribution": ATTRIBUTION,
        "features": features,
    }
