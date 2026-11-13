# Avvio in locale con un comando:
#   docker build -t lumen-v2 .
#   docker run -p 8000:8000 -e LUMEN_MODALITA=finto lumen-v2          (senza AWS, modello finto)
#   docker run -p 8000:8000 -e AWS_REGION=eu-central-1 -e AWS_PROFILE=... -v ~/.aws:/root/.aws:ro lumen-v2
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY documenti ./documenti
COPY scripts ./scripts
# Indice di prova costruito con embeddings finti; con AWS si usa LUMEN_INDICE=s3://.../indice
RUN LUMEN_MODALITA=finto LUMEN_INDICE=/app/indice-finto python scripts/costruisci_indice.py
ENV LUMEN_INDICE=/app/indice-finto

RUN useradd --create-home lumen
USER lumen
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
