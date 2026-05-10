FROM python:3.11-slim
WORKDIR /seed
RUN pip install --no-cache-dir httpx redis
COPY seed_mind.py .
CMD ["python", "-u", "seed_mind.py"]
