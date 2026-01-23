"""Orquestração do fluxo principal do coletor FIES."""

from src.core import build_browser, shutdown_browser
from src.scraping import run_scraper


def main() -> None:
    ctx = build_browser()
    try:
        run_scraper(ctx)
    finally:
        shutdown_browser(ctx)


if __name__ == "__main__":
    main()
