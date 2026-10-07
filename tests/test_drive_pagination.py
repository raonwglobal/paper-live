import json

from paper_live.data_lake import GoogleDriveApiClient


def test_list_files_follows_drive_next_page_token(monkeypatch):
    client = GoogleDriveApiClient(access_token="test-token")
    responses = iter(
        [
            {"files": [{"id": "1", "name": "trade_date=2026-01-01", "mimeType": "application/vnd.google-apps.folder"}], "nextPageToken": "page-2"},
            {"files": [{"id": "2", "name": "trade_date=2026-01-02", "mimeType": "application/vnd.google-apps.folder"}]},
        ]
    )
    urls = []

    def fake_request(method, url, data=None, content_type="application/json"):
        urls.append(url)
        return json.dumps(next(responses)).encode("utf-8")

    monkeypatch.setattr(client, "_request", fake_request)

    files = client.list_files(parent_id="dataset", name_prefix="trade_date=")

    assert [item["id"] for item in files] == ["1", "2"]
    assert "pageToken=page-2" in urls[1]
