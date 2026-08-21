import pytest

from src.osm_edit_mcp import valhalla


def _encode_polyline6(points):
    output = []
    previous = [0, 0]
    for point in points:
        current = [round(point[0] * 1_000_000), round(point[1] * 1_000_000)]
        for value, old in zip(current, previous):
            delta = value - old
            encoded = ~(delta << 1) if delta < 0 else delta << 1
            while encoded >= 0x20:
                output.append(chr((0x20 | (encoded & 0x1F)) + 63))
                encoded >>= 5
            output.append(chr(encoded + 63))
        previous = current
    return "".join(output)


class Response:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


class Client:
    def __init__(self, response, **kwargs):
        self.response = response
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json):
        self.request = (url, json)
        return self.response


def test_decode_polyline6_round_trip():
    points = [(41.123456, 44.654321), (41.123499, 44.654399)]
    assert valhalla.decode_polyline6(_encode_polyline6(points)) == points


@pytest.mark.asyncio
async def test_local_valhalla_match_reports_unmatched_spans(monkeypatch):
    shape = [(41.0, 44.0), (41.0001, 44.0001)]
    response = Response(
        {
            "shape": _encode_polyline6(shape),
            "matched_points": [
                {"type": "matched", "edge_index": 0},
                {"type": "unmatched"},
            ],
            "edges": [{"osm_id": 12}, {"osm_id": 12}],
        }
    )
    monkeypatch.setattr(
        valhalla.httpx,
        "AsyncClient",
        lambda **kwargs: Client(response, **kwargs),
    )

    result = await valhalla.match_track(shape)

    assert result["matched_percent"] == 50.0
    assert result["unmatched_spans"] == [{"start_point_index": 1, "end_point_index": 1}]
    assert result["osm_way_ids"] == [12]
    assert result["matched_geometry"] == shape


@pytest.mark.asyncio
async def test_valhalla_must_remain_local(monkeypatch):
    monkeypatch.setattr(
        valhalla.config, "osm_valhalla_url", "https://routing.example.com"
    )

    with pytest.raises(ValueError, match="must be local"):
        await valhalla.match_track([(1.0, 2.0), (1.1, 2.1)])
