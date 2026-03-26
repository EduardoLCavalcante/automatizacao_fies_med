"""Ponto de entrada da automação FIES."""

import sys
from pathlib import Path

# Garante que o diretório do projeto esteja no sys.path para resolver src.*
sys.path.append(str(Path(__file__).resolve().parent))

from src.app import main


if __name__ == "__main__":
    main(sys.argv[1:])
