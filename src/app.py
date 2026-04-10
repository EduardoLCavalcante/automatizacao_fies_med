"""Orquestração do fluxo principal do coletor FIES."""

import argparse
from typing import Sequence

import src.config.settings as settings
from src.core import build_browser, shutdown_browser
from src.scraping import run_scraper, run_checker, run_review, run_faltantes_txt


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
    parser.add_argument(
        "--modalidade",
        choices=["social", "regular"],
        default=None,
        help="Define modalidade FIES (social ou regular).",
    )
    parser.add_argument(
        "--fies-regular",
        action="store_true",
        help="Atalho para forçar modalidade regular (equivalente a --modalidade regular).",
    )
    parser.add_argument(
        "--faltantes-txt",
        nargs="?",
        const="",
        default=None,
        help="Executa apenas alvos de um TXT de faltantes (padrão por modalidade se omitido).",
    )
    args = parser.parse_args(argv)

    modalidade = None
    if args.fies_regular:
        modalidade = "regular"
    elif args.modalidade:
        modalidade = args.modalidade

    if modalidade:
        settings.FIES_MODALIDADE = modalidade
        print(f"📋 Modalidade FIES selecionada: {modalidade.upper()}")

    ctx = build_browser()
    try:
        if args.faltantes_txt is not None:
            caminho_faltantes = args.faltantes_txt or None
            run_faltantes_txt(ctx, caminho_txt=caminho_faltantes)
        elif args.review:
            run_review(ctx)
        elif args.check:
            run_checker(ctx)
        else:
            run_scraper(ctx)
    finally:
        shutdown_browser(ctx)


if __name__ == "__main__":
    main()
