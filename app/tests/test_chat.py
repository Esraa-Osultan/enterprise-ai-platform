import io


def _upload_sample_doc(client, auth_headers):
    content = (
        b"Radar Calibration Guide.\n"
        b"To calibrate radar sensor X, connect the diagnostic tool and run the auto-align routine. "
        b"The system shall log every calibration attempt. "
        b"The technician must verify the alignment output before closing the panel."
    )
    files = {"file": ("radar_manual.txt", io.BytesIO(content), "text/plain")}
    response = client.post("/upload", files=files, headers=auth_headers)
    return response.json()["doc_id"]


def test_chat_returns_answer_with_sources(client, auth_headers):
    _upload_sample_doc(client, auth_headers)

    response = client.post(
        "/chat", json={"question": "How do I calibrate radar sensor X?"}, headers=auth_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert len(body["sources"]) >= 1
    assert body["sources"][0]["filename"] == "radar_manual.txt"


def test_chat_with_no_documents_returns_no_info_message(client, auth_headers):
    response = client.post("/chat", json={"question": "Anything?"}, headers=auth_headers)
    assert response.status_code == 200
    assert "No relevant information" in response.json()["answer"]


def test_search_returns_ranked_chunks(client, auth_headers):
    _upload_sample_doc(client, auth_headers)

    response = client.post("/search", json={"query": "calibration routine"}, headers=auth_headers)
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) >= 1
    assert "score" in results[0]


def test_summary_endpoint(client, auth_headers):
    doc_id = _upload_sample_doc(client, auth_headers)
    response = client.get(f"/documents/{doc_id}/summary", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["summary"]


def test_requirements_endpoint_finds_shall_and_must(client, auth_headers):
    doc_id = _upload_sample_doc(client, auth_headers)
    response = client.get(f"/documents/{doc_id}/requirements", headers=auth_headers)
    assert response.status_code == 200
    requirements = response.json()["requirements"]
    assert any("shall" in r.lower() for r in requirements)
    assert any("must" in r.lower() for r in requirements)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
