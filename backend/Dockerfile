FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/app ./app
COPY backend/manage.py backend/worker.py backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY backend/demo_documents ./demo_documents
COPY backend/business_documents ./business_documents
RUN useradd --create-home --uid 10001 support && mkdir -p /app/storage /app/.model_cache /data/chroma && chown -R support:support /app /data
USER support
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate && python manage.py adopt-legacy && python manage.py unify-assistant-history && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
