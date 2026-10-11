FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN useradd --create-home --uid 10001 opsagent && chown -R opsagent:opsagent /app
USER opsagent

EXPOSE 8000
CMD ["sh", "-c", "python scripts/validate_production.py && python scripts/bootstrap_database.py && exec python scripts/run_api.py"]
