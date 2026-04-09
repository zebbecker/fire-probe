"""Tests for probe.py."""

from unittest.mock import MagicMock

import requests

from probe import (
    CSV_FIELDNAMES,
    _extract_newest_t,
    append_rows,
    probe_collection,
)


def make_feature(t: str) -> dict:
    """Make a GeoJSON feature with the given FEDS timestep value."""
    return {"type": "Feature", "properties": {"t": t}, "geometry": None}


def make_response(status_code: int, features: list | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"type": "FeatureCollection", "features": features or []}
    return resp


class TestExtractNewestT:
    def test_single_feature(self):
        assert (
            _extract_newest_t([make_feature("2026-04-08T00:00:00")])
            == "2026-04-08T00:00:00"
        )

    def test_picks_newest(self):
        features = [
            make_feature("2024-01-10T00:00:00"),
            make_feature("2024-01-15T12:00:00"),
            make_feature("2024-01-12T00:00:00"),
        ]
        assert _extract_newest_t(features) == "2024-01-15T12:00:00"

    def test_am_before_pm_same_day(self):
        # PM timestep (12:00) is newer than AM timestep (00:00) on the same date
        features = [
            make_feature("2026-04-08T00:00:00"),
            make_feature("2026-04-08T12:00:00"),
        ]
        assert _extract_newest_t(features) == "2026-04-08T12:00:00"

    def test_empty_list(self):
        assert _extract_newest_t([]) == ""

    def test_missing_t_property(self):
        features = [{"type": "Feature", "properties": {}, "geometry": None}]
        assert _extract_newest_t(features) == ""


class TestProbeCollection:
    def test_successful_probe(self):
        session = MagicMock()
        session.get.return_value = make_response(
            200, [make_feature("2026-04-08T00:00:00")]
        )
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == 200
        assert row["newest_feature_datetime"] == "2026-04-08T00:00:00"
        assert row["collection_id"] == "test.collection"
        assert isinstance(row["response_time_ms"], int)
        assert "+00:00" in row["probe_time"]  # probe_time is UTC

    def test_empty_collection(self):
        session = MagicMock()
        session.get.return_value = make_response(200, [])
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == 200
        assert row["newest_feature_datetime"] == ""

    def test_server_error(self):
        session = MagicMock()
        session.get.return_value = make_response(500)
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == 500
        assert row["newest_feature_datetime"] == ""

    def test_timeout(self):
        session = MagicMock()
        session.get.side_effect = requests.Timeout()
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == "TIMEOUT"
        assert row["newest_feature_datetime"] == ""
        assert row["probe_time"]

    def test_request_exception(self):
        session = MagicMock()
        session.get.side_effect = requests.ConnectionError("refused")
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == "ERROR:ConnectionError"
        assert row["newest_feature_datetime"] == ""

    def test_sortby_fallback_on_400(self):
        session = MagicMock()
        session.get.side_effect = [
            make_response(400),
            make_response(200, [make_feature("2026-04-08T00:00:00")]),
        ]
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == 200
        assert row["newest_feature_datetime"] == "2026-04-08T00:00:00"
        assert session.get.call_count == 2

    def test_sortby_fallback_on_422(self):
        session = MagicMock()
        session.get.side_effect = [
            make_response(422),
            make_response(200, [make_feature("2026-04-08T00:00:00")]),
        ]
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == 200
        assert session.get.call_count == 2

    def test_no_sortby_fallback_on_other_errors(self):
        """A 500 should not trigger the sortby fallback."""
        session = MagicMock()
        session.get.return_value = make_response(500)
        probe_collection(session, "test.collection")

        assert session.get.call_count == 1

    def test_json_parse_error_preserves_http_status(self):
        """A non-JSON body on a 200 response should preserve the HTTP status."""
        session = MagicMock()
        resp = make_response(200)
        resp.json.side_effect = ValueError("no JSON object could be decoded")
        resp.text = "<html>error</html>"
        session.get.return_value = resp
        row = probe_collection(session, "test.collection")

        assert row["http_status"] == 200
        assert row["newest_feature_datetime"] == ""


class TestAppendRows:
    def _make_row(self) -> dict:
        return {
            "probe_time": "2026-04-08T04:00:00+00:00",
            "http_status": 200,
            "response_time_ms": 150,
            "newest_feature_datetime": "2026-04-08T00:00:00",
            "collection_id": "test.col",
        }

    def test_creates_file_with_headers(self, tmp_path):
        csv_path = tmp_path / "results.csv"
        append_rows([self._make_row()], csv_path)

        lines = csv_path.read_text().splitlines()
        assert lines[0] == ",".join(CSV_FIELDNAMES)
        assert len(lines) == 2

    def test_appends_without_duplicate_header(self, tmp_path):
        csv_path = tmp_path / "results.csv"
        append_rows([self._make_row()], csv_path)
        append_rows([self._make_row()], csv_path)

        lines = csv_path.read_text().splitlines()
        assert lines.count(",".join(CSV_FIELDNAMES)) == 1
        assert len(lines) == 3  # header + 2 data rows

    def test_creates_parent_directory(self, tmp_path):
        csv_path = tmp_path / "nested" / "dir" / "results.csv"
        append_rows([self._make_row()], csv_path)
        assert csv_path.exists()

    def test_writes_multiple_rows(self, tmp_path):
        csv_path = tmp_path / "results.csv"
        rows = [self._make_row(), self._make_row()]
        append_rows(rows, csv_path)

        lines = csv_path.read_text().splitlines()
        assert len(lines) == 3  # header + 2 rows
