import json
import subprocess
import sys
import time

import requests

BASE = "http://localhost:8000"

# 1. start server
proc = subprocess.Popen(
    ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
    stdout=open("/tmp/uvicorn_smoke.log", "w"),
    stderr=subprocess.STDOUT,
)

try:
    # 2. wait for health check
    for _ in range(30):
        try:
            r = requests.get(f"{BASE}/health", timeout=2)
            if r.status_code == 200:
                print("health:", r.json())
                break
        except requests.exceptions.ConnectionError:
            time.sleep(0.5)
    else:
        print("SERVER NEVER CAME UP")
        sys.exit(1)

    # 3. register
    r = requests.post(
        f"{BASE}/auth/register",
        json={"username": "demo_engineer", "email": "demo@valeo.com", "password": "demo12345"},
        timeout=5,
    )
    print("register:", r.status_code, r.json())

    # 4. login
    r = requests.post(
        f"{BASE}/auth/login",
        data={"username": "demo_engineer", "password": "demo12345"},
        timeout=5,
    )
    print("login:", r.status_code)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 5. upload
    content = (
        b"Radar Calibration Guide.\n"
        b"To calibrate radar sensor X, connect the diagnostic tool and run the auto-align routine. "
        b"The system shall log every calibration attempt. "
        b"The technician must verify the alignment output before closing the panel."
    )
    files = {"file": ("radar_manual.txt", content, "text/plain")}
    r = requests.post(f"{BASE}/upload", headers=headers, files=files, timeout=10)
    print("upload:", r.status_code, r.json())
    doc_id = r.json()["doc_id"]

    # 6. chat
    r = requests.post(
        f"{BASE}/chat",
        headers=headers,
        json={"question": "How do I calibrate radar sensor X?"},
        timeout=10,
    )
    print("chat:", r.status_code, json.dumps(r.json(), indent=2))

    # 7. search
    r = requests.post(
        f"{BASE}/search", headers=headers, json={"query": "auto-align routine"}, timeout=10
    )
    print("search:", r.status_code, json.dumps(r.json(), indent=2))

    # 8. summary
    r = requests.get(f"{BASE}/documents/{doc_id}/summary", headers=headers, timeout=10)
    print("summary:", r.status_code, r.json())

    # 9. requirements
    r = requests.get(f"{BASE}/documents/{doc_id}/requirements", headers=headers, timeout=10)
    print("requirements:", r.status_code, r.json())

    # 10. list documents
    r = requests.get(f"{BASE}/documents", headers=headers, timeout=5)
    print("list documents:", r.status_code, r.json())

    # 11. delete
    r = requests.delete(f"{BASE}/documents/{doc_id}", headers=headers, timeout=5)
    print("delete:", r.status_code, r.json())

    # 12. unauthorized check
    r = requests.get(f"{BASE}/documents", timeout=5)
    print("unauthorized status (expect 401):", r.status_code)

    # 13. docs page
    r = requests.get(f"{BASE}/docs", timeout=5)
    print("swagger docs status (expect 200):", r.status_code)

    print("\nALL SMOKE TESTS COMPLETED")

finally:
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
