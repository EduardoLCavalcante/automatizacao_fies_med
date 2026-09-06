"""Select2: uma abertura por operação, com espera e recuperação após falha."""

import re
import time
import unicodedata
from typing import Iterable, List

from selenium.common.exceptions import (
    NoSuchElementException, StaleElementReferenceException,
    TimeoutException, WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from src.core import BrowserContext, aguardar_captcha
from src.core.retry import aguardar_pagina_responsiva


class OpcaoIndisponivel(RuntimeError):
    """O Select2 terminou de carregar e não oferece uma opção inequívoca."""


MAX_TENTATIVAS = 3
POLL_SECONDS = 0.2
# A estabilidade é necessária apenas ao enumerar uma lista inteira. Para uma
# seleção, a própria opção alvo é a confirmação e não deve ficar esperando o
# término de requisições sem relação com aquele campo.
ESTABILIDADE_SECONDS_FAST = 0.12
ESTABILIDADE_SECONDS_NORMAL = 0.5


def _norm_text(txt: str) -> str:
    norm = unicodedata.normalize("NFD", txt or "")
    return " ".join(norm.encode("ascii", "ignore").decode("ascii").lower().split())


def _codigo_final(txt: str) -> str | None:
    match = re.search(r"\((\d{4,})\)\s*$", txt or "")
    return match.group(1) if match else None


def _nome_sem_codigo(txt: str) -> str:
    return re.sub(r"\(\d{4,}\)\s*$", "", txt or "").strip()


def _texto_selecionado(atual: str, esperado: str) -> bool:
    if _codigo_final(esperado):
        return _codigo_final(atual) == _codigo_final(esperado)
    atual_norm = _norm_text(_nome_sem_codigo(atual))
    esperado_norm = _norm_text(_nome_sem_codigo(esperado))
    # O portal acrescenta a UF ao nome do estado.
    return bool(esperado_norm) and (
        atual_norm == esperado_norm
        or bool(re.fullmatch(re.escape(esperado_norm) + r"\s*-\s*[a-z]{2}", atual_norm))
    )


def _limite(ctx: BrowserContext) -> float:
    return 45 if ctx.fast_mode else 60


def _esperar(ctx, deadline, condicao):
    restante = deadline - time.monotonic()
    if restante <= 0:
        raise TimeoutException("tempo da operação Select2 esgotado")
    return WebDriverWait(
        ctx.driver, restante, poll_frequency=POLL_SECONDS,
        ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
    ).until(condicao)


def _estado(ctx, cid):
    # Somente leitura: consulta o select nativo e o wrapper atual, nunca cache.
    return ctx.driver.execute_script("""
        const label = document.getElementById(arguments[0]);
        if (!label) return null;
        const wrapper = label.closest('.select2-container');
        const selection = label.closest('.select2-selection') || label;
        const originalId = arguments[0].replace(/^select2-/, '').replace(/-container$/, '');
        const original = document.getElementById(originalId);
        const selected = original && [...original.selectedOptions].find(o => o.value);
        return {
            text: label.getAttribute('title') || label.textContent || '',
            selected: original ? Boolean(selected) : Boolean(label.getAttribute('title')),
            disabled: Boolean(original?.disabled)
                || Boolean(wrapper?.classList.contains('select2-container--disabled'))
                || selection.getAttribute('aria-disabled') === 'true',
            open: selection.getAttribute('aria-expanded') === 'true',
            visible: Boolean(label.getClientRects().length),
            element: label
        };
    """, cid)


def _confirmado(ctx, cid, texto):
    state = _estado(ctx, cid)
    return bool(state and not state['disabled']
                and state['selected'] and (texto is None or _texto_selecionado(state['text'], texto)))


def _pronto(ctx, cid):
    state = _estado(ctx, cid)
    if not state or state['disabled']:
        return False
    return state['element'] if state['visible'] else False


def esperar_select2_habilitado(ctx: BrowserContext, container_id: str, timeout: int | None = None):
    return _esperar(ctx, time.monotonic() + (timeout or _limite(ctx)),
                    lambda _: _pronto(ctx, container_id))


def _resultados(ctx, cid):
    el = ctx.driver.find_element(By.ID, cid.removesuffix('-container') + '-results')
    return el if el.is_displayed() else False


def _abrir(ctx, cid, deadline):
    container = _esperar(ctx, deadline, lambda _: _pronto(ctx, cid))
    if not _estado(ctx, cid)['open']:
        container.click()
    _esperar(ctx, deadline, lambda _: _resultados(ctx, cid))


def _fechar(ctx, cid):
    state = _estado(ctx, cid)
    if state and state['open']:
        ctx.driver.find_element(By.ID, cid).find_element(
            By.XPATH, "ancestor::*[contains(@class,'select2-selection')][1]"
        ).send_keys(Keys.ESCAPE)


def _buscar(ctx, cid, texto, deadline):
    def campo_visivel(_):
        results = _resultados(ctx, cid)
        if not results:
            return False
        dropdown = results.find_element(
            By.XPATH, "ancestor::*[contains(concat(' ',normalize-space(@class),' '),' select2-dropdown ')][1]"
        )
        campos = dropdown.find_elements(By.CSS_SELECTOR, 'input.select2-search__field')
        return next((el for el in campos if el.is_displayed()), False)
    campo = _esperar(ctx, deadline, campo_visivel)
    campo.send_keys(Keys.CONTROL + 'a')
    campo.send_keys(Keys.BACKSPACE)
    campo.send_keys(_nome_sem_codigo(texto))


def _opcoes_visiveis(ctx, cid):
    """Uma leitura do DOM por poll, independente de requisições de outros campos."""
    results = _resultados(ctx, cid)
    if not results:
        return None
    return ctx.driver.execute_script("""
        const results = arguments[0];
        const id = arguments[1].replace(/^select2-/, '').replace(/-container$/, '');
        const original = document.getElementById(id);
        const adapter = window.jQuery && original
            ? window.jQuery(original).data('select2')?.dataAdapter : null;
        const request = adapter?._request;
        const pending = request && typeof request.readyState === 'number'
            && request.readyState !== 4 && request.statusText !== 'abort';
        return {
            loading: Boolean(pending || results.querySelector(
                '.loading-results, .select2-results__option--loading')),
            message: [...results.querySelectorAll('.select2-results__message')]
                .map(el => el.innerText.trim()).join(' '),
            options: [...results.querySelectorAll(
                '.select2-results__option[aria-selected], .select2-results__option--selectable'
            )].filter(el => el.getAttribute('aria-disabled') !== 'true')
              .map(el => el.innerText.trim()).filter(Boolean),
            more: Boolean(results.querySelector('.select2-results__option--load-more')),
            element: results
        };
    """, results, cid)


def _opcoes_validas(dados):
    return [texto for texto in dados['options']
            if not _norm_text(texto).startswith(('selecione', '-- selecione'))]


def _verificar_mensagem(dados, cid):
    mensagem = _norm_text(dados['message'])
    if mensagem and not any(t in mensagem for t in (
        'no results', 'nenhum resultado', 'nenhuma correspondencia'
    )):
        raise WebDriverException(f"Select2 {cid}: {dados['message']}")


def _proxima_pagina(ctx, dados):
    ctx.driver.execute_script(
        'arguments[0].scrollTop = arguments[0].scrollHeight', dados['element']
    )


def _listar_aberto(ctx, cid, deadline):
    """Enumera todas as páginas na mesma abertura."""
    acumuladas = dict()
    anterior = None
    estavel_desde = time.monotonic()

    def ler(_):
        nonlocal anterior, estavel_desde
        dados = _opcoes_visiveis(ctx, cid)
        if not dados or dados['loading']:
            anterior = None
            estavel_desde = time.monotonic()
            return False
        _verificar_mensagem(dados, cid)
        textos = _opcoes_validas(dados)
        acumuladas.update(dict.fromkeys(textos))
        if dados['more']:
            _proxima_pagina(ctx, dados)
            anterior = None
            estavel_desde = time.monotonic()
            return False
        assinatura = (tuple(textos), dados['message'])
        if assinatura != anterior:
            anterior = assinatura
            estavel_desde = time.monotonic()
            return False
        estabilidade = ESTABILIDADE_SECONDS_FAST if ctx.fast_mode else ESTABILIDADE_SECONDS_NORMAL
        if time.monotonic() - estavel_desde < estabilidade:
            return False
        if not textos and not dados['message']:
            return False
        return (list(acumuladas),)

    return _esperar(ctx, deadline, ler)[0]


def _candidato(opcoes, texto, tolerante=False):
    if texto is None:
        return opcoes[0] if opcoes else None
    exatas = [op for op in opcoes if _texto_selecionado(op, texto)]
    if len(exatas) == 1:
        return exatas[0]
    # Nunca escolhe a primeira IES arbitrariamente ou ignora código solicitado.
    if tolerante and not _codigo_final(texto):
        alvo = _norm_text(texto)
        aproximadas = [op for op in opcoes if alvo in _norm_text(_nome_sem_codigo(op))]
        if len(aproximadas) == 1:
            return aproximadas[0]
    return None


def _clicar_opcao(ctx, cid, alvo, deadline):
    def encontrar(_):
        results = _resultados(ctx, cid)
        if not results:
            return False
        return ctx.driver.execute_script("""
            return [...arguments[0].querySelectorAll('.select2-results__option')]
                .find(el => el.innerText.trim() === arguments[1]
                    && el.getAttribute('aria-disabled') !== 'true') || null;
        """, results, alvo)
    # O polling só localiza; o clique ocorre uma única vez.
    _esperar(ctx, deadline, encontrar).click()


def _aguardar_alvo(ctx, cid, texto, tolerante, deadline):
    """Para no alvo inequívoco; só pagina se ainda for necessário procurá-lo."""
    acumuladas = dict()

    def pronto(_):
        dados = _opcoes_visiveis(ctx, cid)
        if not dados or dados['loading']:
            return False
        _verificar_mensagem(dados, cid)
        acumuladas.update(dict.fromkeys(_opcoes_validas(dados)))
        candidato = _candidato(list(acumuladas), texto, tolerante)
        # Código identifica a IES mesmo quando ainda há páginas. Sem código,
        # termina a enumeração para não aceitar uma correspondência ambígua.
        if candidato and (texto is None or _codigo_final(texto) or not dados['more']):
            return candidato
        if dados['more']:
            _proxima_pagina(ctx, dados)
            return False
        if acumuladas or dados['message']:
            raise OpcaoIndisponivel(f"{cid}: opção indisponível ou ambígua: {texto}")
        return False  # DOM vazio sem resposta conclusiva continua aguardando.
    return _esperar(ctx, deadline, pronto)


def _operar(ctx, cid, texto=None, *, listar=False, tolerante=False):
    esperado = texto
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        deadline = time.monotonic() + _limite(ctx)
        try:
            _esperar(ctx, deadline, lambda _: _pronto(ctx, cid))
            if not listar and _confirmado(ctx, cid, esperado):
                _fechar(ctx, cid)
                return []
            _abrir(ctx, cid, deadline)
            if texto is not None:
                _buscar(ctx, cid, texto, deadline)
            if listar:
                opcoes = _listar_aberto(ctx, cid, deadline)
                _fechar(ctx, cid)
                return opcoes
            alvo = _aguardar_alvo(ctx, cid, texto, tolerante, deadline)
            esperado = alvo
            _clicar_opcao(ctx, cid, alvo, deadline)
            _esperar(ctx, deadline, lambda _: _confirmado(ctx, cid, esperado))
            _fechar(ctx, cid)
            return []
        except OpcaoIndisponivel:
            _fechar(ctx, cid)
            raise
        except WebDriverException as exc:
            print(f"Select2: campo={cid} alvo={texto or 'primeira opção/listagem'} "
                  f"tentativa={tentativa}/{MAX_TENTATIVAS} falha={type(exc).__name__}: {exc.msg}")
            if tentativa == MAX_TENTATIVAS:
                raise
            ctx.select2_retries += 1
            # Recuperação não reaplica filtros; o próximo ciclo relê o valor real.
            if aguardar_pagina_responsiva(ctx, timeout=30):
                aguardar_captcha(ctx)
            try:
                _fechar(ctx, cid)
            except WebDriverException:
                pass


def select2(ctx: BrowserContext, container_id: str, texto: str) -> None:
    _operar(ctx, container_id, texto)


def select2_exact(ctx: BrowserContext, container_id: str, texto: str) -> None:
    _operar(ctx, container_id, texto)


def curso_existe(ctx: BrowserContext, nome_curso: str) -> bool:
    """Consulta isolada; o pipeline seleciona diretamente para não abrir duas vezes."""
    return _candidato(listar_opcoes_select2(ctx, 'select2-noCursosPublico-container'), nome_curso) is not None


def listar_opcoes_select2(ctx: BrowserContext, container_id: str) -> List[str]:
    return sorted(_operar(ctx, container_id, listar=True))


def listar_opcoes_select2_rapido(ctx: BrowserContext, container_id: str) -> List[str]:
    return listar_opcoes_select2(ctx, container_id)[:10]


def select2_pick_first(ctx: BrowserContext, container_id: str) -> bool:
    try:
        _operar(ctx, container_id)
        return True
    except (OpcaoIndisponivel, WebDriverException):
        return False


def _verify_select2_selected(ctx: BrowserContext, container_id: str, expected_text: str, timeout: int = 6) -> bool:
    try:
        return bool(_esperar(ctx, time.monotonic() + timeout, lambda _: _confirmado(ctx, container_id, expected_text)))
    except WebDriverException:
        return False


def _resolver_container(ctx, container_ids):
    ids = tuple(container_ids)
    def existente(_):
        for cid in ids:
            elementos = ctx.driver.find_elements(By.ID, cid)
            if any(el.is_displayed() for el in elementos):
                return cid
        return False
    return _esperar(ctx, time.monotonic() + _limite(ctx), existente)


def select2_exact_multi(ctx: BrowserContext, container_ids: Iterable[str], texto: str) -> bool:
    try:
        cid = _resolver_container(ctx, container_ids)
        _operar(ctx, cid, texto, tolerante=True)
        return True
    except (OpcaoIndisponivel, WebDriverException):
        return False


def listar_opcoes_select2_multi(ctx: BrowserContext, container_ids: Iterable[str]) -> List[str]:
    return listar_opcoes_select2(ctx, _resolver_container(ctx, container_ids))
