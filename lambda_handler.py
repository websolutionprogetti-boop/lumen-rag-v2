"""Adattatore per AWS Lambda: la stessa app FastAPI risponde dietro l'indirizzo della funzione (Function URL)."""
from mangum import Mangum

from app.api import app

handler = Mangum(app, lifespan="off")
