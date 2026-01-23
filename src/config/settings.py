"""Configurações centrais do coletor FIES."""

FAST_MODE: bool = True  # acelera a execução para evitar expiração de sessão/CAPTCHA
CONCEITO_ALVO = None  # reservado para uso futuro (ex.: forçar conceito específico)
BASE_URL = "https://fiesselecaoaluno.mec.gov.br/consulta"

CSV_COLUMNS = [
    "estado",
    "municipio",
    "curso",
    "ies",
    "conceito_curso",
    "nota_ultimo_aprovado",
    "nota_enem_ultimo_ampla",
    "nota_enem_ultimo_ppiq",
    "nota_enem_ultimo_pcd",
]
