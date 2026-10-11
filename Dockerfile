FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# An empty API URL makes browser requests use the same Render origin.
ENV VITE_API_URL=""
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend-build /frontend/dist /app/frontend/dist

RUN useradd --create-home --uid 10001 opsagent && chown -R opsagent:opsagent /app
USER opsagent

EXPOSE 8000
CMD ["sh", "-c", "python scripts/validate_production.py && python scripts/bootstrap_database.py && exec python scripts/run_api.py"]
