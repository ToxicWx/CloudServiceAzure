FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Запуск від звичайного користувача, а не root (безпека)
RUN useradd -m appuser && mkdir -p /data && chown appuser /data
USER appuser

ENV LOCAL_STORAGE_DIR=/data
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "--timeout", "120", "app:app"]
