"""
CloudDrop — хмарний сервіс обміну файлами.

Файли зберігаються в Azure Blob Storage (якщо задано AZURE_STORAGE_CONNECTION_STRING),
інакше — локально на диску (режим для тестування без хмари).
"""
import os
import secrets
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import (Flask, abort, jsonify, redirect, render_template, request,
                   send_from_directory, url_for)
from werkzeug.utils import secure_filename

MAX_MB = int(os.getenv("MAX_UPLOAD_MB", "50"))
LINK_HOURS = int(os.getenv("LINK_HOURS", "24"))
CONTAINER = os.getenv("AZURE_STORAGE_CONTAINER", "uploads")
CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "").strip()
LOCAL_DIR = Path(os.getenv("LOCAL_STORAGE_DIR", "/tmp/clouddrop"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024


# ---------------------------------------------------------------- сховища
class LocalStorage:
    mode = "local"

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, file_id, filename, stream, content_type):
        folder = self.root / file_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / filename).write_bytes(stream.read())

    def find(self, file_id):
        folder = self.root / file_id
        if not folder.is_dir():
            return None
        files = list(folder.iterdir())
        return files[0].name if files else None

    def download_url(self, file_id, filename):
        return url_for("local_file", file_id=file_id, filename=filename)

    def stats(self):
        files = [p for p in self.root.rglob("*") if p.is_file()]
        return len(files), sum(p.stat().st_size for p in files)


class AzureBlobStorage:
    mode = "azure-blob"

    def __init__(self, conn_str, container):
        from azure.storage.blob import BlobServiceClient
        self.service = BlobServiceClient.from_connection_string(conn_str)
        self.container = self.service.get_container_client(container)
        try:
            self.container.create_container()
        except Exception:
            pass  # контейнер вже існує
        self.account_name = self.service.account_name
        self.account_key = self.service.credential.account_key

    def save(self, file_id, filename, stream, content_type):
        from azure.storage.blob import ContentSettings
        self.container.upload_blob(
            name=f"{file_id}/{filename}",
            data=stream,
            content_settings=ContentSettings(
                content_type=content_type or "application/octet-stream",
                content_disposition=f'attachment; filename="{filename}"'),
        )

    def find(self, file_id):
        for blob in self.container.list_blobs(name_starts_with=f"{file_id}/"):
            return blob.name.split("/", 1)[1]
        return None

    def download_url(self, file_id, filename):
        # Тимчасове посилання (SAS-токен), що діє LINK_HOURS годин
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas
        blob_name = f"{file_id}/{filename}"
        sas = generate_blob_sas(
            account_name=self.account_name,
            container_name=self.container.container_name,
            blob_name=blob_name,
            account_key=self.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=LINK_HOURS),
        )
        return f"{self.container.get_blob_client(blob_name).url}?{sas}"

    def stats(self):
        count = size = 0
        for blob in self.container.list_blobs():
            count += 1
            size += blob.size or 0
        return count, size


storage = AzureBlobStorage(CONN_STR, CONTAINER) if CONN_STR else LocalStorage(LOCAL_DIR)


# ---------------------------------------------------------------- маршрути
@app.get("/")
def index():
    return render_template("index.html", max_mb=MAX_MB, mode=storage.mode,
                           host=socket.gethostname())


@app.post("/upload")
def upload():
    file = request.files.get("file")
    if not file or not file.filename:
        return render_template("index.html", max_mb=MAX_MB, mode=storage.mode,
                               host=socket.gethostname(),
                               error="Оберіть файл"), 400
    filename = secure_filename(file.filename) or "file"
    file_id = secrets.token_urlsafe(6)
    storage.save(file_id, filename, file.stream, file.mimetype)
    link = url_for("get_file", file_id=file_id, _external=True)
    return render_template("done.html", link=link, filename=filename,
                           hours=LINK_HOURS, mode=storage.mode,
                           host=socket.gethostname())


@app.get("/f/<file_id>")
def get_file(file_id):
    filename = storage.find(file_id)
    if not filename:
        abort(404)
    return redirect(storage.download_url(file_id, filename))


@app.get("/local/<file_id>/<path:filename>")
def local_file(file_id, filename):
    if storage.mode != "local":
        abort(404)
    return send_from_directory(LOCAL_DIR / file_id, filename, as_attachment=True)


@app.get("/health")
def health():
    count, size = storage.stats()
    return jsonify(status="ok", storage=storage.mode, host=socket.gethostname(),
                   files=count, total_mb=round(size / 1024 / 1024, 2),
                   time=datetime.now(timezone.utc).isoformat())


@app.errorhandler(413)
def too_large(_):
    return render_template("index.html", max_mb=MAX_MB, mode=storage.mode,
                           host=socket.gethostname(),
                           error=f"Файл завеликий (максимум {MAX_MB} МБ)"), 413


@app.errorhandler(404)
def not_found(_):
    return render_template("index.html", max_mb=MAX_MB, mode=storage.mode,
                           host=socket.gethostname(),
                           error="Файл не знайдено"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
