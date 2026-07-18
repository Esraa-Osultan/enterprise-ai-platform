"""
Every authenticated user shares one FAISS index and one users.json file,
so nothing stops user A's request from touching user B's documents unless
every read/write path explicitly filters by owner. These tests exist
because that filtering was previously missing entirely: any logged-in
user could list, search, chat over, summarize, or delete any other
user's uploaded documents.
"""

import io


def _upload(client, headers, filename, text):
    files = {"file": (filename, io.BytesIO(text.encode()), "text/plain")}
    response = client.post("/upload", files=files, headers=headers)
    assert response.status_code == 200
    return response.json()["doc_id"]


def test_list_documents_does_not_include_other_users_docs(client, auth_headers, other_auth_headers):
    _upload(client, auth_headers, "mine.txt", "Only engineer1 should see this file.")
    _upload(client, other_auth_headers, "theirs.txt", "Only engineer2 should see this file.")

    mine = client.get("/documents", headers=auth_headers).json()["documents"]
    theirs = client.get("/documents", headers=other_auth_headers).json()["documents"]

    assert [d["filename"] for d in mine] == ["mine.txt"]
    assert [d["filename"] for d in theirs] == ["theirs.txt"]


def test_cannot_delete_another_users_document(client, auth_headers, other_auth_headers):
    doc_id = _upload(client, auth_headers, "mine.txt", "Belongs to engineer1.")

    response = client.delete(f"/documents/{doc_id}", headers=other_auth_headers)
    assert response.status_code == 404

    # still there for the actual owner
    mine = client.get("/documents", headers=auth_headers).json()["documents"]
    assert any(d["doc_id"] == doc_id for d in mine)


def test_cannot_summarize_another_users_document(client, auth_headers, other_auth_headers):
    doc_id = _upload(client, auth_headers, "mine.txt", "Belongs to engineer1.")

    response = client.get(f"/documents/{doc_id}/summary", headers=other_auth_headers)
    assert response.status_code == 404


def test_search_only_returns_own_chunks(client, auth_headers, other_auth_headers):
    _upload(client, auth_headers, "mine.txt", "The gizmo calibration procedure is secret.")
    _upload(client, other_auth_headers, "theirs.txt", "The gizmo calibration procedure is secret.")

    response = client.post(
        "/search", json={"query": "gizmo calibration procedure"}, headers=other_auth_headers
    )
    results = response.json()["results"]
    assert len(results) >= 1
    assert all(r["filename"] == "theirs.txt" for r in results)
