FROM python:3.11-slim
WORKDIR /foundation
RUN pip install --no-cache-dir redis
COPY foundation_mind.py .
CMD ["python", "-u", "foundation_mind.py"]
