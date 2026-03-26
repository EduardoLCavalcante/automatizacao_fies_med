"""Orquestração do fluxo principal do coletor FIES."""

import argparse
from typing import Sequence

from src.core import build_browser, shutdown_browser
from src.scraping import run_scraper, run_checker, run_review


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Coletor FIES")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Executa apenas checagem de cobertura (UF/Município/Curso/IES) sem pesquisar notas",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="Executa exatamente o mesmo fluxo padrão (alias do modo normal)",
    )
    args = parser.parse_args(argv)

    ctx = build_browser()
    try:
        if args.review:
            run_review(ctx)
        elif args.check:
            run_checker(ctx)
        else:
            run_scraper(ctx)
    finally:
        shutdown_browser(ctx)


if __name__ == "__main__":
    main()
