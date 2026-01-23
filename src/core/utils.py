"""Funções utilitárias compartilhadas."""

import random
import time
from typing import Optional


def human_delay(fast_mode: bool, a: Optional[float] = None, b: Optional[float] = None) -> None:
    """Simula digitação/click humano com pequenas variações."""
    if a is None or b is None:
        a, b = (0.15, 0.45) if fast_mode else (1.5, 3.5)
    time.sleep(random.uniform(a, b))


def normalizar_decimal_pt(texto: Optional[str]) -> Optional[str]:
    """Converte separadores PT-BR para formato de ponto, quando aplicável."""
    if not texto:
        return None
    try:
        return texto.replace(".", "").replace(",", ".")
    except Exception:
        return texto
