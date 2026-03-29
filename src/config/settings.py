"""Configurações centrais do coletor FIES."""

from enum import Enum
from typing import Literal


class FiesModalidade(str, Enum):
    """Modalidades FIES disponíveis para seleção."""
    SOCIAL = "social"    # FIES Social (CadÚnico) - stCadunicoS
    REGULAR = "regular"  # FIES Regular - stCadunicoN
    AMBOS = "ambos"      # Coleta ambas modalidades


FAST_MODE: bool = True  # acelera a execução para evitar expiração de sessão/CAPTCHA
CONCEITO_ALVO = None  # reservado para uso futuro (ex.: forçar conceito específico)
BASE_URL = "https://fiesselecaoaluno.mec.gov.br/consulta"

# Modalidade FIES a ser coletada (pode ser sobrescrita via --modalidade)
FIES_MODALIDADE: FiesModalidade = FiesModalidade.SOCIAL

CSV_COLUMNS = [
    "estado",
    "municipio",
    "curso",
    "ies",
    "modalidade_fies",  # "social" ou "regular"
    "conceito_curso",
    "nota_ultimo_aprovado",
    "nota_enem_ultimo_ampla",
    "nota_enem_ultimo_ppiq",
    "nota_enem_ultimo_pcd",
]

# Configurações de retry para tratamento de timeout
MAX_RETRIES: int = 3  # número padrão de tentativas
RETRY_DELAY: float = 2.0  # delay base entre tentativas (segundos)
MAX_RETRY_DELAY: float = 30.0  # delay máximo entre tentativas
USE_EXPONENTIAL_BACKOFF: bool = True  # usar backoff exponencial

# Arquivos de log de timeout
TIMEOUT_LOG_FILE: str = "timeout_log.jsonl"
TIMEOUT_METRICS_FILE: str = "timeout_metrics.json"
FAILED_ITEMS_FILE: str = "failed_items.json"

# Habilitar/desabilitar logging de timeout
TIMEOUT_LOGGING_ENABLED: bool = True
