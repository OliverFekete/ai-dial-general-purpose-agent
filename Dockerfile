FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY task/ ./task/

ENV PYTHONPATH=/app \
    DIAL_API_KEY=${DIAL_API_KEY} \
    DEPLOYMENT_NAME=${DEPLOYMENT_NAME} \
    DIAL_ENDPOINT=${DIAL_ENDPOINT} \
    PYINTERPRETER_MCP_URL=${PYINTERPRETER_MCP_URL} \
    DDG_MCP_URL=${DDG_MCP_URL}

EXPOSE 8000

CMD ["python", "task/app.py"]

