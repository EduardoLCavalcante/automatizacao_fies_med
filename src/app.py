"""Orquestração do fluxo principal do coletor FIES."""

import argparse
from typing import Sequence

from src.config import FiesModalidade
from src.core import build_browser, shutdown_browser
from src.scraping import run_scraper, run_checker, run_review


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Coletor FIES - Scraper de notas de corte",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python main.py                        # Coleta FIES Social (padrão)
  python main.py --modalidade regular   # Coleta apenas FIES Regular
  python main.py --modalidade ambos     # Coleta ambas modalidades
  python main.py --check                # Apenas verifica cobertura
        """,
    )
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
        choices=["social", "regular", "ambos"],
        default=None,
        metavar="TIPO",
        help=(
            "Modalidade FIES a coletar: "
            "'social' (FIES Social/CadÚnico), "
            "'regular' (FIES padrão), "
            "'ambos' (coleta as duas modalidades). "
            "Padrão: usa valor de FIES_MODALIDADE em settings.py"
        ),
    )
    args = parser.parse_args(argv)
    
    # Se modalidade foi especificada via CLI, sobrescrever configuração global
    modalidade = None
    if args.modalidade:
        import src.config.settings as settings
        settings.FIES_MODALIDADE = FiesModalidade(args.modalidade)
        modalidade = args.modalidade
        print(f"📋 Modalidade FIES selecionada: {args.modalidade.upper()}")

    ctx = build_browser()
    try:
        if modalidade == "ambos":
            # Modo "ambos": executa duas passadas, uma para cada modalidade
            print("\n" + "=" * 50)
            print("🔄 MODO AMBOS: Executando para FIES Social")
            print("=" * 50 + "\n")
            
            if args.review:
                run_review(ctx, modalidade="social")
            elif args.check:
                run_checker(ctx, modalidade="social")
            else:
                run_scraper(ctx, modalidade="social")
            
            print("\n" + "=" * 50)
            print("🔄 MODO AMBOS: Executando para FIES Regular")
            print("=" * 50 + "\n")
            
            if args.review:
                run_review(ctx, modalidade="regular")
            elif args.check:
                run_checker(ctx, modalidade="regular")
            else:
                run_scraper(ctx, modalidade="regular")
            
            print("\n" + "=" * 50)
            print("✅ MODO AMBOS: Coleta completa para as duas modalidades")
            print("=" * 50)
        else:
            if args.review:
                run_review(ctx, modalidade=modalidade)
            elif args.check:
                run_checker(ctx, modalidade=modalidade)
            else:
                run_scraper(ctx, modalidade=modalidade)
    finally:
        shutdown_browser(ctx)


if __name__ == "__main__":
    main()
