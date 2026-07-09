import io


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
