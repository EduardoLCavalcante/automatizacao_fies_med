from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager
import time
import random
import pandas as pd

# =============================
# CONFIGURAÇÃO
# =============================
FAST_MODE = True  # acelera a execução para evitar expiração de sessão/CAPTCHA
CONCEITO_ALVO = None  # ex.: "A" para forçar um conceito específico; None usa o primeiro disponível
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
options.add_argument("--disable-blink-features=AutomationControlled")
options.page_load_strategy = "none" if FAST_MODE else "normal"

driver = webdriver.Chrome(
    service=Service(ChromeDriverManager().install()),
    options=options
)

wait = WebDriverWait(driver, 25 if FAST_MODE else 60)

def human_delay(a=None, b=None):
    if a is None or b is None:
        a, b = (0.15, 0.45) if FAST_MODE else (1.5, 3.5)
    time.sleep(random.uniform(a, b))

# Colunas fixas do CSV para garantir headers consistentes
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

# =============================
# ACESSO AO SITE
# =============================
driver.get("https://fiesselecaoaluno.mec.gov.br/consulta")
input("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
try:
    wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
except TimeoutException:
    pass

# =============================
# RECARREGAR PÁGINA + CAPTCHA
# =============================
def recarregar_e_esperar(estado, municipio=None):
    driver.get("https://fiesselecaoaluno.mec.gov.br/consulta")
    print("⚠️ Resolva o CAPTCHA e pressione ENTER para continuar...")
    input()
    try:
        wait.until(EC.presence_of_element_located((By.ID, "select2-noEstado-container")))
    except TimeoutException:
        pass
    # Reaplica filtros essenciais: Estado e, opcionalmente, Município e Curso
    try:
        select2("select2-noEstado-container", estado)
        human_delay(0.2, 0.5) if FAST_MODE else time.sleep(2)
    except Exception:
        return False
    if municipio:
        try:
            select2("select2-noMunicipio-container", municipio)
            human_delay(0.2, 0.5) if FAST_MODE else human_delay(1, 2)
        except Exception:
            return False
        try:
            select2_exact("select2-noCursosPublico-container", "MEDICINA")
            human_delay(0.2, 0.5) if FAST_MODE else human_delay(1, 2)
        except TimeoutException:
            print("⚠️ Não foi possível selecionar MEDICINA após recarregar")
            return False
    return True

# =============================
# SELECT2 GENÉRICO
# =============================
def select2(container_id, texto):
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    campo = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//input[contains(@class,'select2-search__field')]")
        )
    )

    campo.send_keys(Keys.CONTROL + "a")
    campo.send_keys(Keys.BACKSPACE)

    per_char = 0.02 if FAST_MODE else 0.06
    for letra in texto:
        campo.send_keys(letra)
        time.sleep(per_char)

    if FAST_MODE:
        human_delay(0.08, 0.18)
    else:
        time.sleep(1)
    campo.send_keys(Keys.ENTER)

def select2_exact(container_id, texto):
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    campo = wait.until(
        EC.visibility_of_element_located(
            (By.XPATH, "//input[contains(@class,'select2-search__field')]")
        )
    )

    # Limpa e digita o texto alvo
    campo.send_keys(Keys.CONTROL + "a")
    campo.send_keys(Keys.BACKSPACE)
    per_char = 0.02 if FAST_MODE else 0.06
    for letra in texto:
        campo.send_keys(letra)
        time.sleep(per_char)
    if FAST_MODE:
        human_delay(0.08, 0.18)
    else:
        time.sleep(0.8)

    # Abre/garante a lista de resultados
    results = wait.until(
        EC.presence_of_element_located(
            (By.CLASS_NAME, "select2-results__options")
        )
    )

    match = None
    last_count = -1
    while True:
        itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
        for item in itens:
            txt = item.text.strip()
            if txt and txt.upper() == texto.upper():
                match = item
                break

        if match:
            break

        if len(itens) == last_count:
            break
        last_count = len(itens)
        # Rola para carregar mais opções (caso haja)
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", results
        )
        if FAST_MODE:
            human_delay(0.06, 0.14)
        else:
            time.sleep(0.6)

    if match:
        match.click()
        human_delay(0.4, 0.9)
    else:
        # Como fallback, fecha e não seleciona nada
        driver.find_element(By.TAG_NAME, "body").click()
        raise TimeoutException(f"Opção exata não encontrada para: {texto}")

    driver.find_element(By.TAG_NAME, "body").click()

# =============================
# VERIFICA SE CURSO EXISTE (RÁPIDO)
# =============================
def curso_existe(nome_curso):
    try:
        container = wait.until(
            EC.element_to_be_clickable((By.ID, "select2-noCursosPublico-container"))
        )
        container.click()

        campo = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//input[contains(@class,'select2-search__field')]")
            )
        )

        campo.send_keys(nome_curso)
        # Em FAST_MODE reduz a espera antes de ler as opções
        human_delay(0.1, 0.2) if 'FAST_MODE' in globals() and FAST_MODE else time.sleep(1)

        WebDriverWait(driver, 3 if ('FAST_MODE' in globals() and FAST_MODE) else 5).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, "select2-results__option")
            )
        )

        opcoes = driver.find_elements(By.CLASS_NAME, "select2-results__option")
        existe = any(nome_curso.upper() in o.text.upper() for o in opcoes)

        driver.find_element(By.TAG_NAME, "body").click()
        return existe

    except TimeoutException:
        driver.find_element(By.TAG_NAME, "body").click()
        return False

# =============================
# LISTAR OPÇÕES SELECT2
# =============================
def listar_opcoes_select2(container_id):
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()
    # aguarda lista aparecer sem dormir fixo

    results = wait.until(
        EC.presence_of_element_located(
            (By.CLASS_NAME, "select2-results__options")
        )
    )

    opcoes = set()
    last_count = 0

    while True:
        itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
        for item in itens:
            txt = item.text.strip()
            if txt and "Selecione" not in txt:
                opcoes.add(txt)

        if len(opcoes) == last_count:
            break

        last_count = len(opcoes)
        driver.execute_script(
            "arguments[0].scrollTop = arguments[0].scrollHeight", results
        )
        time.sleep(0.8)

    driver.find_element(By.TAG_NAME, "body").click()
    return sorted(opcoes)

def listar_opcoes_select2_rapido(container_id):
    container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
    container.click()

    results = wait.until(
        EC.presence_of_element_located(
            (By.CLASS_NAME, "select2-results__options")
        )
    )

    itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
    opcoes = []
    for item in itens[:10]:  # pega rapidamente as primeiras opções visíveis
        txt = item.text.strip()
        if txt and "Selecione" not in txt:
            opcoes.append(txt)

    driver.find_element(By.TAG_NAME, "body").click()
    return opcoes

def select2_pick_first(container_id):
    try:
        container = wait.until(EC.element_to_be_clickable((By.ID, container_id)))
        container.click()
        results = wait.until(EC.presence_of_element_located((By.CLASS_NAME, "select2-results__options")))
        itens = results.find_elements(By.CLASS_NAME, "select2-results__option")
        alvo = None
        for item in itens:
            txt = item.text.strip()
            if txt and "Selecione" not in txt and "No results" not in txt:
                alvo = item
                break
        if not alvo and itens:
            alvo = itens[0]
        if alvo:
            alvo.click()
            driver.find_element(By.TAG_NAME, "body").click()
            return True
    except Exception:
        pass
    try:
        driver.find_element(By.TAG_NAME, "body").click()
    except Exception:
        pass
    return False

def selecionar_radio_por_texto(texto):
    alvo = texto.strip()

    # 1) Procura radios e seus labels associados, tenta clicar no label
    radios = driver.find_elements(By.XPATH, "//input[@type='radio']")
    for r in radios:
        lbl = None
        try:
            lbl = r.find_element(By.XPATH, "following-sibling::label")
        except:
            pass
        if not lbl:
            try:
                lbl = r.find_element(By.XPATH, "ancestor::label")
            except:
                pass

        if lbl:
            txt = lbl.text.strip()
            if txt and alvo.upper() in txt.upper():
                try:
                    driver.execute_script("arguments[0].click()", lbl)
                except:
                    lbl.click()
                # Aguarda marcar
                try:
                    WebDriverWait(driver, 5).until(lambda d: r.is_selected())
                except TimeoutException:
                    pass
                human_delay(0.2, 0.6)
                return True

    # 2) Procura diretamente por label em qualquer lugar da página
    labels = driver.find_elements(By.XPATH, "//label")
    for lbl in labels:
        txt = lbl.text.strip()
        if txt and alvo.upper() in txt.upper():
            try:
                driver.execute_script("arguments[0].click()", lbl)
            except:
                lbl.click()
            human_delay(0.2, 0.6)
            return True

    # 3) Fallback: tenta clicar no próprio input que tem label ao lado
    try:
        radio = wait.until(
            EC.element_to_be_clickable(
                (By.XPATH, f"//input[@type='radio' and following-sibling::label[contains(normalize-space(.), '{alvo}')]]")
            )
        )
        driver.execute_script("arguments[0].click()", radio)
        human_delay(0.2, 0.6)
        return True
    except TimeoutException:
        return False

def selecionar_radio_fies_social():
    alvo = "Fies Social"
    if selecionar_radio_por_texto(alvo):
        # Verifica se algum radio com esse label está marcado
        try:
            marcado = driver.find_elements(By.XPATH, "//input[@type='radio' and (following-sibling::label[contains(normalize-space(.), 'Fies Social')] or ancestor::label[contains(normalize-space(.), 'Fies Social')]) and @checked]")
            if marcado:
                return True
        except Exception:
            pass
    # Fallback: clicar diretamente no label com texto
    try:
        lbl = wait.until(EC.element_to_be_clickable((By.XPATH, "//label[contains(normalize-space(.), 'Fies Social')]")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", lbl)
        try:
            lbl.click()
        except Exception:
            driver.execute_script("arguments[0].click();", lbl)
        human_delay(0.2, 0.6)
        return True
    except Exception:
        pass
    # Fallback extra: qualquer elemento clicável com o texto
    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[self::label or self::span or self::div or self::button][contains(normalize-space(.), 'Fies Social')]")))
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)
        human_delay(0.2, 0.6)
        return True
    except Exception:
        return False

    # =============================
    # MODAL: EXTRAI NOTA ENEM
    # =============================
def extrair_nota_enem_de_modal():
    # Aguarda o label "NOTA ENEM" no modal
    try:
        label = wait.until(
            EC.visibility_of_element_located(
                (By.XPATH, "//span[contains(normalize-space(.), 'NOTA ENEM')]")
            )
        )
    except TimeoutException:
        return None
    # Tenta pegar o primeiro span em negrito após o label
    valor_span = None
    candidatos = [
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[contains(@style,'font-weight')][1]",
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[contains(@style,'font-size')][1]",
        "//span[contains(normalize-space(.), 'NOTA ENEM')]/following::span[1]",
    ]
    for xp in candidatos:
        try:
            valor_span = wait.until(
                EC.visibility_of_element_located((By.XPATH, xp))
            )
            if valor_span and valor_span.text.strip():
                break
        except TimeoutException:
            continue
    nota_texto = valor_span.text.strip() if valor_span else None
    # Fecha o modal pelo botão "Voltar" (btnModalFechar) quando disponível
    try:
        btn_voltar = wait.until(EC.element_to_be_clickable((By.ID, "btnModalFechar")))
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_voltar)
        except Exception:
            pass
        try:
            btn_voltar.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn_voltar)
        # Aguarda o modal desaparecer
        try:
            WebDriverWait(driver, 5).until(
                EC.invisibility_of_element_located((By.ID, "btnModalFechar"))
            )
        except TimeoutException:
            pass
    except TimeoutException:
        # Fallback: ESC ou botão fechar genérico
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            try:
                fechar = driver.find_element(By.XPATH, "//div[contains(@class,'modal')]//button[contains(@class,'close') or contains(.,'Fechar')]")
                driver.execute_script("arguments[0].click();", fechar)
            except Exception:
                pass
    return nota_texto

def extrair_nota_enem_de_linha(linha):
    try:
        btn = linha.find_element(By.XPATH, ".//button[contains(., 'Ver Detalhes')]")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
        btn.click()
        return extrair_nota_enem_de_modal()
    except Exception:
        return None

def expandir_todos_candidatos():
    # Aguarda a tabela aparecer
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
            )
        )
    except TimeoutException:
        return

    # Clica "Ver mais" até não haver mais crescimento e o botão deixar de estar clicável
    max_clicks = 500
    sem_crescimento = 0
    localizadores = [
        (By.ID, "linkPaginacaoPublico"),
        (By.XPATH, "//span[contains(@class,'link-ver-mais-consulta') and contains(., 'Ver mais')]")
    ]

    def _get_ver_mais():
        for by, sel in localizadores:
            els = driver.find_elements(by, sel)
            for el in els:
                try:
                    if el.is_displayed():
                        return el
                except Exception:
                    continue
        return None

    def _rows_count():
        return len(driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr"))

    while max_clicks > 0:
        max_clicks -= 1
        qtd_antes = _rows_count()

        ver_mais_el = _get_ver_mais()
        if not ver_mais_el:
            break

        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ver_mais_el)
        except Exception:
            pass
        clicked = False
        try:
            ver_mais_el.click()
            clicked = True
        except Exception:
            try:
                driver.execute_script("arguments[0].click();", ver_mais_el)
                clicked = True
            except Exception:
                clicked = False

        if not clicked:
            break

        # Poll rápido por crescimento de linhas ou botão sumir/deixar de exibir
        timeout = 2.0 if FAST_MODE else 5.0
        end = time.time() + timeout
        cresceu = False
        while time.time() < end:
            qtd_atual = _rows_count()
            if qtd_atual > qtd_antes:
                cresceu = True
                break
            # se o botão não estiver mais visível, parar
            if _get_ver_mais() is None:
                break
            time.sleep(0.05 if FAST_MODE else 0.15)

        if not cresceu:
            sem_crescimento += 1
            if sem_crescimento >= 2:
                try:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                except Exception:
                    pass
                break
        else:
            sem_crescimento = 0

        # Folga mínima entre cliques
        if FAST_MODE:
            time.sleep(0.05)
        else:
            human_delay(0.1, 0.2)

def obter_ultima_linha():
    # Garante que a tabela está presente e totalmente expandida, então retorna o último <tr>
    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
            )
        )
    except TimeoutException:
        return None

    expandir_todos_candidatos()

    linhas = driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
    if not linhas:
        return None
    return linhas[-1]

def normalizar_decimal_pt(texto):
    if not texto:
        return None
    try:
        return texto.replace('.', '').replace(',', '.')
    except Exception:
        return texto

def selecionar_categoria(tipo_label=None, tipo_codigo=None):
    alvos = []
    if tipo_codigo is not None:
        alvos.append((By.XPATH, f"//button[contains(@onclick,'selecaoClassificaoTipoVaga({tipo_codigo})')]") )
    if tipo_label:
        alvos.append((By.XPATH, f"//button[contains(normalize-space(.), '{tipo_label}')]") )

    # Conta linhas antes para detectar atualização
    try:
        linhas_antes = driver.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")
        qtd_antes = len(linhas_antes)
    except Exception:
        qtd_antes = 0

    btn = None
    for by, sel in alvos:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel)))
            if el and el.is_displayed():
                btn = el
                break
        except TimeoutException:
            continue

    if not btn:
        return False

    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
    except Exception:
        pass
    try:
        btn.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", btn)
        except Exception:
            return False

    # Aguarda mudança de contagem de linhas ou seleção visual do botão
    try:
        WebDriverWait(driver, 8).until(
            lambda d: len(d.find_elements(By.XPATH, "//table[@id='listaResultadoConsulta']//tr | //table/tbody/tr")) != qtd_antes
        )
    except TimeoutException:
        pass
    return True

# =============================
# SELECT2 AUXILIARES (ROBUSTO PARA IES)
# =============================
def _verify_select2_selected(container_id, expected_text, timeout=6):
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: (d.find_element(By.ID, container_id).get_attribute("title") or d.find_element(By.ID, container_id).text).strip().upper() == expected_text.strip().upper()
        )
        return True
    except Exception:
        return False

def select2_exact_multi(container_ids, texto):
    for cid in container_ids:
        try:
            select2_exact(cid, texto)
            if _verify_select2_selected(cid, texto):
                return True
        except Exception:
            continue
    return False

def listar_opcoes_select2_multi(container_ids):
    # Tenta listar opções em múltiplos containers; aguarda pequenas janelas para opções surgirem
    for cid in container_ids:
        try:
            op = listar_opcoes_select2(cid)
            if op:
                return op
            # Se vazio, dá uma pequena folga e tenta novamente uma vez
            human_delay(0.1, 0.2)
            op2 = listar_opcoes_select2(cid)
            if op2:
                return op2
        except Exception:
            continue
    return []

# =============================
# BUSCA POR MUNICÍPIO
# =============================
def buscar_notas_por_municipio(municipio, estado):
    resultados = []

    select2("select2-noMunicipio-container", municipio)
    human_delay(0.2, 0.5) if FAST_MODE else human_delay(1, 2)

    # 🔥 AQUI ESTÁ O GANHO DE PERFORMANCE
    if not curso_existe("MEDICINA"):
        print("⏭️ Sem Medicina — pulando")
        return resultados

    # Seleciona o curso MEDICINA por correspondência exata para evitar BIOMEDICINA
    try:
        select2_exact("select2-noCursosPublico-container", "MEDICINA")
    except TimeoutException:
        print("⚠️ Não foi possível selecionar MEDICINA (exato)")
        return resultados
    human_delay(0.2, 0.5) if FAST_MODE else human_delay(1, 2)

    ies_container_ids = [
        "select2-iesPublico-container",      
    ]
    ies_lista = listar_opcoes_select2_multi(ies_container_ids)
    if not ies_lista:
        return resultados

    for idx, ies in enumerate(ies_lista):
        print(f"🏫 IES ({idx+1}/{len(ies_lista)}): {ies}")
        ok_ies = select2_exact_multi(ies_container_ids, ies)
        if not ok_ies:
            print(f"⚠️ IES não selecionada: {ies} — registrando com notas ausentes")
            resultados.append({
                "municipio": municipio,
                "curso": "MEDICINA",
                "ies": ies,
                "conceito_curso": None,
                "nota_ultimo_aprovado": None,
                "nota_enem_ultimo_ampla": None,
                "nota_enem_ultimo_ppiq": None,
                "nota_enem_ultimo_pcd": None,
            })
            continue
        human_delay(0.2, 0.5) if FAST_MODE else human_delay(1, 2)

        # Aguarda o Select2 de CONCEITO aparecer após selecionar a IES
        conceito_container_ids = [
            "select2-conceitoCurso-container",
        ]
        conceito_container_presente = None
        for cid in conceito_container_ids:
            try:
                wait.until(EC.presence_of_element_located((By.ID, cid)))
                conceito_container_presente = cid
                break
            except TimeoutException:
                continue

        if not conceito_container_presente:
            print("⚠️ Select2 de conceito não disponível após IES")
            continue

        # Sempre há uma única opção de conceito: selecione a primeira
        conceito_valor = None
        if not select2_pick_first(conceito_container_presente):
            print("⚠️ Não foi possível selecionar o conceito")
            continue
        else:
            try:
                elc = driver.find_element(By.ID, conceito_container_presente)
                conceito_valor = (elc.get_attribute("title") or elc.text or "").strip()
            except Exception:
                conceito_valor = None

        # Seleciona o radio "Fies Social" antes de pesquisar
        if not selecionar_radio_fies_social():
            print("⚠️ Radio 'Fies Social' não encontrado/selecionável")

        # Clica no botão Pesquisar pelo id fornecido
        try:
            wait.until(EC.element_to_be_clickable((By.ID, "btnBuscarCursos"))).click()
        except TimeoutException:
            # Fallback: tenta localizar por input com value 'Pesquisar'
            try:
                wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@id='btnBuscarCursos' or (@type='button' and @value='Pesquisar')]"))).click()
            except TimeoutException:
                print("⚠️ Botão 'Pesquisar' não clicável")

        try:
            wait.until(EC.presence_of_element_located((By.XPATH, "//table/tbody/tr")))
        except:
            continue

        # Expande todos os candidatos, clicando "Ver mais" até sumir
        expandir_todos_candidatos()

        # Mantém a nota do último candidato da categoria padrão após lista completa
        ultima = obter_ultima_linha()
        nota = None
        if ultima:
            try:
                tds = ultima.find_elements(By.TAG_NAME, "td")
                if len(tds) >= 5:
                    nota = tds[4].text.replace(",", ".")
            except Exception:
                nota = None

        # Para cada categoria, seleciona, expande e pega ENEM do último candidato
        categorias = [
            ("Ampla", 1, "nota_enem_ultimo_ampla"),
            ("PPIQ", 3, "nota_enem_ultimo_ppiq"),
            ("PCD", 2, "nota_enem_ultimo_pcd"),
        ]
        enem_por_categoria = {}
        for label, codigo, chave in categorias:
            ok = selecionar_categoria(tipo_label=label, tipo_codigo=codigo)
            if not ok:
                enem_por_categoria[chave] = None
                continue
            # Garante lista completa e usa o último <tr>
            ultima_cat = obter_ultima_linha()
            if not ultima_cat:
                enem_por_categoria[chave] = None
                continue
            try:
                nota_enem = extrair_nota_enem_de_linha(ultima_cat)
            except Exception:
                nota_enem = None
            enem_por_categoria[chave] = normalizar_decimal_pt(nota_enem) if nota_enem else None

        resultados.append({
            "municipio": municipio,
            "curso": "MEDICINA",
            "ies": ies,
            "conceito_curso": conceito_valor,
            "nota_ultimo_aprovado": nota,
            "nota_enem_ultimo_ampla": enem_por_categoria.get("nota_enem_ultimo_ampla"),
            "nota_enem_ultimo_ppiq": enem_por_categoria.get("nota_enem_ultimo_ppiq"),
            "nota_enem_ultimo_pcd": enem_por_categoria.get("nota_enem_ultimo_pcd"),
        })

        # Removido refresh por IES; refresh ocorrerá por município no loop principal
    
    return resultados

# =============================
# EXECUÇÃO
# =============================
ESTADOS = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AP": "Amapá",
    "AM": "Amazonas",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais",
    "PA": "Pará",
    "PB": "Paraíba",
    "PR": "Paraná",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul",
    "RO": "Rondônia",
    "RR": "Roraima",
    "SC": "Santa Catarina",
    "SP": "São Paulo",
    "SE": "Sergipe",
    "TO": "Tocantins"
}
dados_finais = []

for uf, estado in ESTADOS.items():
    print(f"\n🟦 Estado: {estado}")
    # Recarrega a página ao trocar de Estado e reaplica somente o Estado
    ok_estado = recarregar_e_esperar(estado)
    if not ok_estado:
        print("⚠️ Não foi possível recarregar e selecionar o Estado; avançando para o próximo")
        continue
    human_delay(0.2, 0.5) if FAST_MODE else time.sleep(2)

    municipios = listar_opcoes_select2("select2-noMunicipio-container")
    print(f"➡️ {len(municipios)} municípios")

    for i, municipio in enumerate(municipios):
        print(f"📍 {municipio}")
        try:
            res = buscar_notas_por_municipio(municipio, estado)
            for r in res:
                dados_finais.append({"estado": uf, **r})
        except:
            pass

        pd.DataFrame(dados_finais).reindex(columns=CSV_COLUMNS).to_csv(
            "notas_fies_medicina.csv",
            index=False,
            encoding="utf-8-sig"
        )

        human_delay(0.3, 0.7) if FAST_MODE else human_delay(2, 4)

        # Recarrega página e prepara o próximo município (evita repetir o atual)
        if i < len(municipios) - 1:
            proximo_municipio = municipios[i + 1]
            ok = recarregar_e_esperar(estado, proximo_municipio)
            if not ok:
                print("⚠️ Não foi possível recarregar/preparar próximo município; tentando continuar mesmo assim")

driver.quit()
print("\n✅ FINALIZADO")
