FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir numpy fastapi "uvicorn[standard]"
COPY flip7 flip7
COPY server server
COPY models models
COPY analysis analysis
RUN mkdir -p runs
EXPOSE 8077
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8077"]
