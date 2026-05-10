FROM python:3.11-slim
WORKDIR /worker
RUN pip install --no-cache-dir httpx redis
COPY worker.py .
CMD ["python", "-u", "worker.py"]
