"""Protezioni di spesa: tetto mensile di domande per tutta la demo e limite di domande al minuto per visitatore.

Il tetto mensile vive su DynamoDB (una riga per mese, contatore atomico): raggiunto il tetto la chat va in pausa
e il mese successivo riparte da sola, perché la riga del mese nuovo parte da zero.
Senza tabella (test e prove locali) il contatore resta in memoria.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone


def mese_corrente() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class TettoMensile:
    def __init__(self, tetto: int, tabella: str = "", regione: str = "eu-central-1"):
        self.tetto = tetto
        self.tabella = tabella
        self.regione = regione
        self._memoria: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def consuma(self) -> bool:
        """Conta una domanda. Restituisce False se il tetto del mese è già raggiunto."""
        mese = mese_corrente()
        if not self.tabella:
            with self._lock:
                if self._memoria[mese] >= self.tetto:
                    return False
                self._memoria[mese] += 1
                return True
        import boto3
        from botocore.exceptions import ClientError

        try:
            boto3.client("dynamodb", region_name=self.regione).update_item(
                TableName=self.tabella,
                Key={"mese": {"S": mese}},
                UpdateExpression="ADD domande :uno",
                ConditionExpression="attribute_not_exists(domande) OR domande < :tetto",
                ExpressionAttributeValues={":uno": {"N": "1"}, ":tetto": {"N": str(self.tetto)}},
            )
            return True
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise


class LimiteAlMinuto:
    """Finestra scorrevole in memoria, come nella v1 (ogni istanza Lambda ha la sua)."""

    def __init__(self, massimo: int, finestra: float = 60.0):
        self.massimo = massimo
        self.finestra = finestra
        self._visite: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def troppe(self, chi: str) -> bool:
        ora = time.monotonic()
        with self._lock:
            coda = self._visite[chi]
            while coda and ora - coda[0] >= self.finestra:
                coda.popleft()
            if len(coda) >= self.massimo:
                return True
            coda.append(ora)
            if len(self._visite) > 5000:
                for k in [k for k, v in self._visite.items() if not v]:
                    del self._visite[k]
            return False
