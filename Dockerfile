FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/data/backups

ENV DATA_DIR=/app/data
ENV DB_PATH=/app/data/ariamir_tracker.db
ENV BACKUP_DIR=/app/data/backups

CMD ["python", "bot.py"]
