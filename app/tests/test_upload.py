import io
import os

from app.core.config import get_settings


def test_upload_txt_file(client, auth_headers):
    content = b"How to calibrate radar sensor X: turn the dial slowly until the light is green."
    files = {"file": ("manual.txt", io.BytesIO(content), "text/plain")}
    response = client.post("/upload", files=files, headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "manual.txt"
    assert body["num_chunks"] >= 1


def test_upload_unsupported_extension_rejected(client, auth_headers):
    files = {"file": ("virus.exe", io.BytesIO(b"whatever"), "application/octet-stream")}
    response = client.post("/upload", files=files, headers=auth_headers)
    assert response.status_code == 400


def test_upload_requires_auth(client):
    files = {"file": ("manual.txt", io.BytesIO(b"hello world"), "text/plain")}
    response = client.post("/upload", files=files)
    assert response.status_code == 401


def test_list_documents_after_upload(client, auth_headers):
    files = {"file": ("spec.txt", io.BytesIO(b"The system shall support 10 sensors."), "text/plain")}
    client.post("/upload", files=files, headers=auth_headers)

    response = client.get("/documents", headers=auth_headers)
    assert response.status_code == 200
    docs = response.json()["documents"]
    assert len(docs) == 1
    assert docs[0]["filename"] == "spec.txt"


def test_delete_document(client, auth_headers):
    files = {"file": ("temp.txt", io.BytesIO(b"Temporary content for deletion test."), "text/plain")}
    upload_response = client.post("/upload", files=files, headers=auth_headers)
    doc_id = upload_response.json()["doc_id"]

    delete_response = client.delete(f"/documents/{doc_id}", headers=auth_headers)
    assert delete_response.status_code == 200

    docs = client.get("/documents", headers=auth_headers).json()["documents"]
    assert all(d["doc_id"] != doc_id for d in docs)


def test_delete_nonexistent_document_returns_404(client, auth_headers):
    response = client.delete("/documents/does-not-exist", headers=auth_headers)
    assert response.status_code == 404


def test_upload_path_traversal_filename_is_sanitized(client, auth_headers):
    """Regression test for the path-traversal fix in app/api/upload.py.
    Before the fix, `file.filename` was used verbatim in
    `os.path.join(upload_dir, file.filename)`, so a filename like
    "../../evil.txt" could write outside the upload directory. Nothing
    previously asserted this couldn't happen."""
    content = b"Attempted traversal payload."
    files = {"file": ("../../evil.txt", io.BytesIO(content), "text/plain")}
    response = client.post("/upload", files=files, headers=auth_headers)

    assert response.status_code == 200
    # The client-supplied name is kept only for display/citations...
    assert response.json()["filename"] == "evil.txt"

    # ...and nothing was ever written outside the configured upload dir.
    upload_dir = get_settings().upload_dir
    parent_of_upload_dir = os.path.dirname(os.path.abspath(upload_dir))
    assert not os.path.exists(os.path.join(parent_of_upload_dir, "evil.txt"))
    # The upload dir itself should contain exactly one server-generated
    # (uuid-based) filename, not "evil.txt".
    written = os.listdir(upload_dir) if os.path.exists(upload_dir) else []
    assert "evil.txt" not in written


def test_upload_rejects_files_over_size_limit(client, auth_headers, monkeypatch):
    """Regression test for the 25MB ceiling added in app/api/upload.py.
    Uses a monkeypatched limit so the test doesn't need to actually
    allocate/send 25MB."""
    import app.api.upload as upload_module

    monkeypatch.setattr(upload_module, "MAX_UPLOAD_BYTES", 100)

    content = b"x" * 500
    files = {"file": ("big.txt", io.BytesIO(content), "text/plain")}
    response = client.post("/upload", files=files, headers=auth_headers)

    assert response.status_code == 413
    # The partial file must not be left behind on disk.
    upload_dir = get_settings().upload_dir
    assert os.listdir(upload_dir) == [] if os.path.exists(upload_dir) else True


def test_upload_empty_file_returns_422(client, auth_headers):
    """A file that parses but yields no extractable text (e.g. all
    whitespace) should fail cleanly with a 422, not a 500 or a silently
    'successful' zero-chunk document."""
    files = {"file": ("empty.txt", io.BytesIO(b"   \n\n   "), "text/plain")}
    response = client.post("/upload", files=files, headers=auth_headers)
    assert response.status_code == 422
