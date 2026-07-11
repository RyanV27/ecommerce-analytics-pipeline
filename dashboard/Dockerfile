FROM python:3.11-slim

WORKDIR /app

COPY dashboard/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dashboard/ ./dashboard/
COPY ab_testing/ ./ab_testing/

ENV PYTHONPATH=/app

EXPOSE 8080

CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
