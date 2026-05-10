FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir redis[hiredis]
COPY scaler.py .
CMD ["python", "-u", "scaler.py"]
