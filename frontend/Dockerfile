# ── NetVerify Frontend (Streamlit Dashboard) ─────────────
# Build context: ./frontend (see root docker-compose.yml)
# ──────────────────────────────────────────────────────────

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ── Install dependencies ─────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy frontend source code ────────────────────────────
COPY . .

# Remove files that should not be in the image
RUN rm -rf __pycache__/ _legacy/ Dockerfile .dockerignore requirements.txt

# ── Environment ──────────────────────────────────────────
# Backend URL as seen from the Streamlit container (internal Docker network)
ENV NETVERIFY_API_URL=http://backend:8000
# Backend URL as seen from the user's browser (for the JS chatbot widget)
ENV NETVERIFY_PUBLIC_API_URL=http://localhost:8000

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

CMD ["streamlit", "run", "dashboard.py", "--server.port=8501", "--server.address=0.0.0.0"]
