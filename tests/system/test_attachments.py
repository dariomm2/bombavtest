from __future__ import annotations

import uuid

from tests.conftest import response_data


def test_attachment_roundtrip_uses_real_s3_storage(live_admin):
    client, headers = live_admin
    marker = uuid.uuid4().hex[:10]
    filename = f"manual-{marker}.txt"
    content = f"BombAvTest system test {marker}\n".encode()

    draft = response_data(
        client.post(
            "/api/admin/topic-attachment-drafts",
            headers=headers,
            files={"file": (filename, content, "text/plain")},
        )
    )
    draft_download = client.get(draft["download_url"])
    assert draft_download.status_code == 200
    assert draft_download.content == content
    assert draft_download.headers["content-type"].startswith("text/plain")

    topic = response_data(
        client.post(
            "/api/admin/topics",
            headers=headers,
            json={
                "number": f"SYS-{marker}",
                "name": f"System test {marker}",
                "color": "#123456",
                "attachment_draft_ids": [draft["id"]],
            },
        )
    )
    topics = response_data(client.get("/api/admin/topics"))
    created = next(item for item in topics if item["id"] == topic["id"])
    assert len(created["attachments"]) == 1
    attachment = created["attachments"][0]

    final_download = client.get(attachment["download_url"])
    assert final_download.status_code == 200
    assert final_download.content == content
    assert "attachment" in final_download.headers["content-disposition"].lower()
    assert final_download.headers["x-content-type-options"] == "nosniff"

    deleted = client.delete(
        f"/api/admin/topics/{topic['id']}/attachments/{attachment['id']}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert client.get(attachment["download_url"]).status_code == 404

    assert client.delete(f"/api/admin/topics/{topic['id']}", headers=headers).status_code == 200
