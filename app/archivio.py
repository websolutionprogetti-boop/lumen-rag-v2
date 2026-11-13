"""Lettura e scrittura di file da cartella locale o da S3, con lo stesso codice."""
from __future__ import annotations

from pathlib import Path


def _s3(percorso: str) -> tuple[str, str]:
    senza = percorso[len("s3://"):]
    bucket, _, chiave = senza.partition("/")
    return bucket, chiave


def leggi_bytes(percorso: str) -> bytes:
    if percorso.startswith("s3://"):
        import boto3

        bucket, chiave = _s3(percorso)
        return boto3.client("s3").get_object(Bucket=bucket, Key=chiave)["Body"].read()
    return Path(percorso).read_bytes()


def leggi_testo(percorso: str) -> str:
    return leggi_bytes(percorso).decode("utf-8")


def scrivi_bytes(percorso: str, dati: bytes) -> None:
    if percorso.startswith("s3://"):
        import boto3

        bucket, chiave = _s3(percorso)
        boto3.client("s3").put_object(Bucket=bucket, Key=chiave, Body=dati)
        return
    p = Path(percorso)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(dati)
