FROM python:3.11-slim

WORKDIR /app

COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

COPY ml/ ./ml/

ENV PYTHONPATH=/app/ml

# Shared image for the segmentation Cloud Run Job and both Vertex AI training
# jobs — the entry script is supplied as an arg, e.g.:
#   docker run datapulse-ml ml/segmentation.py
#   docker run datapulse-ml ml/repeat_purchase_model.py
#   docker run datapulse-ml ml/forecasting.py
ENTRYPOINT ["python"]
