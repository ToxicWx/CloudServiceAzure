"""Автоматичні тести (запускаються в GitHub Actions перед деплоєм)."""
import io
import os
import sys
import tempfile

os.environ["AZURE_STORAGE_CONNECTION_STRING"] = ""          # тест без хмари
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from app import app  # noqa: E402

client = app.test_client()


def test_home_page():
    r = client.get("/")
    assert r.status_code == 200
    assert "CloudDrop" in r.get_data(as_text=True)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_upload_and_download():
    data = {"file": (io.BytesIO(b"hello cloud"), "test.txt")}
    r = client.post("/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    link = html.split('<div class="link" id="link">')[1].split("</div>")[0]
    path = link.replace("http://localhost", "")

    r = client.get(path, follow_redirects=True)
    assert r.status_code == 200
    assert r.data == b"hello cloud"


def test_missing_file_returns_404():
    assert client.get("/f/doesnotexist").status_code == 404


def test_upload_without_file():
    r = client.post("/upload", data={}, content_type="multipart/form-data")
    assert r.status_code == 400
