# Coletor de Notas FIES — Medicina

Scraper automatizado (Selenium) que percorre os estados e municípios no portal oficial do FIES para coletar informações de cursos de Medicina, salvando resultados continuamente em CSV.

## Visão Geral
- **Navegação automatizada:** Usa Selenium + Chrome para interagir com filtros (Estado, Município, Curso, IES, Conceito).
- **Curso alvo:** Seleção exata de "MEDICINA" (evita confusão com Biomedicina).
- **Categorias:** Coleta notas por categoria (Ampla, PPIQ, PCD) e a nota do último Pré-Selecionado na lista atual.
- **CAPTCHA:** Requer intervenção humana quando solicitado; o script pausa e aguarda confirmação no terminal.
- **Persistência incremental:** Escreve/atualiza o arquivo CSV a cada município processado.

## Requisitos
- **Python 3.9+** (recomendado 3.10+)
- **Google Chrome** instalado (o `webdriver-manager` cuidará do ChromeDriver automaticamente)
- Pacotes Python listados em [requirements.txt](requirements.txt)

## Instalação
Recomendado usar um ambiente virtual.

```bash
# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Windows (CMD)
python -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt

# Linux / macOS (opcional)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Como Executar
```bash
python main.py
```

### Modalidades FIES

O sistema suporta duas modalidades de FIES:

| Modalidade | Descrição | Radio Button |
|------------|-----------|--------------|
| **social** | FIES Social (inscritos no CadÚnico) | `stCadunicoS` |
| **regular** | FIES padrão | `stCadunicoN` |

Para selecionar a modalidade via linha de comando:

```bash
# Coleta apenas FIES Social (padrão)
python main.py --modalidade social

# Coleta apenas FIES Regular
python main.py --modalidade regular

# Coleta ambas modalidades (executa duas passadas)
python main.py --modalidade ambos
```

A coluna `modalidade_fies` é automaticamente adicionada ao CSV para identificar de qual modalidade veio cada registro.

**Nota:** Se `--modalidade` não for especificado, usa o valor padrão definido em `FIES_MODALIDADE` no arquivo `settings.py` (padrão: `social`).

Durante a execução:
- Uma janela do Chrome será aberta em [main.py](main.py) e o site do FIES será carregado.
- Quando o CAPTCHA aparecer, o terminal mostrará a mensagem "Resolva o CAPTCHA e pressione ENTER". Resolva-o no navegador e pressione ENTER no terminal para continuar.
- O script iterará por todos os estados e seus municípios, selecionando o curso de Medicina e as IES disponíveis.
- O arquivo de saída [notas_fies_medicina.csv](notas_fies_medicina.csv) é atualizado continuamente (encoding UTF-8 com BOM para fácil abertura no Excel).

## Saída (CSV)
Arquivo: [notas_fies_medicina.csv](notas_fies_medicina.csv)

Colunas:
- **estado:** UF (ex.: SP, RJ)
- **municipio:** Nome do município consultado
- **curso:** "MEDICINA"
- **ies:** Instituição de Ensino Superior
- **modalidade_fies:** Modalidade FIES ("social" ou "regular")
- **conceito_curso:** Conceito listado após seleção da IES
- **nota_ultimo_aprovado:** Nota (texto numérico) da última linha após expandir a listagem
- **nota_enem_ultimo_ampla:** NOTA ENEM do último candidato na categoria Ampla
- **nota_enem_ultimo_ppiq:** NOTA ENEM do último candidato na categoria PPIQ
- **nota_enem_ultimo_pcd:** NOTA ENEM do último candidato na categoria PCD

Observações:
- Notas podem vir vazias quando não encontradas ou quando a navegação encontra limitações da página.
- Valores numéricos podem aparecer com vírgula no site; o script normaliza onde aplicável.

## Configurações Úteis
No início de [main.py](main.py):
- **`FAST_MODE`**: acelera interações e reduz esperas. Útil para evitar expiração de sessão; se notar instabilidade, defina como `False`.

### Configurações de Retry/Timeout

As seguintes configurações podem ser ajustadas em [src/config/settings.py](src/config/settings.py):

| Configuração | Padrão | Descrição |
|-------------|--------|-----------|
| `MAX_RETRIES` | 3 | Número máximo de tentativas para operações que falham |
| `RETRY_DELAY` | 2.0 | Delay base entre tentativas (segundos) |
| `MAX_RETRY_DELAY` | 30.0 | Delay máximo entre tentativas |
| `USE_EXPONENTIAL_BACKOFF` | True | Usar backoff exponencial (dobra delay a cada retry) |
| `TIMEOUT_LOGGING_ENABLED` | True | Habilita logging de timeouts |
| `TIMEOUT_LOG_FILE` | timeout_log.jsonl | Arquivo de log detalhado de timeouts |
| `TIMEOUT_METRICS_FILE` | timeout_metrics.json | Arquivo com métricas agregadas |
| `FAILED_ITEMS_FILE` | failed_items.json | Lista de itens que falharam para reprocessamento |

## Tratamento de Timeouts

O sistema possui tratamento robusto de timeouts com as seguintes características:

### Retry Automático
- Todas as operações críticas (seleção de filtros, navegação, extração de dados) possuem retry automático
- Usa backoff exponencial por padrão (2s → 4s → 8s) para evitar sobrecarga
- Após falha final, registra item para reprocessamento posterior

### Logs de Timeout
Ao final da execução, são gerados:
- **timeout_log.jsonl**: Log detalhado de cada timeout (timestamp, operação, tentativa, erro)
- **timeout_metrics.json**: Métricas agregadas (total de timeouts, taxa de sucesso de retry, timeouts por operação/estado)
- **failed_items.json**: Lista de itens que falharam completamente para reprocessamento

### Interpretando os Logs

```bash
# Ver resumo de métricas
cat timeout_metrics.json | python -m json.tool

# Contar timeouts por operação
cat timeout_log.jsonl | jq -s 'group_by(.operation) | map({operation: .[0].operation, count: length})'

# Listar estados com mais problemas
cat timeout_metrics.json | python -c "import json,sys; d=json.load(sys.stdin); print(d['timeouts_by_state'])"
```

### Reprocessando Itens Falhados
Itens que falharam após todas as tentativas são salvos em `failed_items.json`. Para reprocessá-los:

```python
# Em uma sessão Python interativa ou script
from src.core.timeout_log import TimeoutLogger
logger = TimeoutLogger.get_instance()
failed = logger.load_failed_items()
for item in failed:
    print(f"{item.estado}/{item.municipio}: {item.last_error}")
```

## Dicas de Uso
- Mantenha o Chrome visível para conseguir interagir com CAPTCHAs quando solicitado.
- Evite usar o computador de forma que atrapalhe os cliques automatizados enquanto o script está rodando.
- A coleta completa (todos os estados/municípios) pode demorar. O CSV é atualizado a cada município, permitindo interromper e já aproveitar os dados coletados.

### Executar apenas alguns estados (opcional)
Edite o dicionário `ESTADOS` em [main.py](main.py) para reduzir o escopo, por exemplo:

```python
ESTADOS = {
    "SP": "São Paulo",
    "RJ": "Rio de Janeiro",
}
```

## Estrutura do Projeto
- [main.py](main.py): ponto de entrada que apenas chama a automação.
- [src/app.py](src/app.py): orquestração do fluxo principal.
- Configuração: [src/config/settings.py](src/config/settings.py) (FAST_MODE, BASE_URL, colunas), [src/config/estados.py](src/config/estados.py) (mapa UF → nome), reexportados por [src/config/__init__.py](src/config/__init__.py).
- Núcleo: [src/core/browser.py](src/core/browser.py) (WebDriver), [src/core/utils.py](src/core/utils.py) (delays/normalização), reexportados por [src/core/__init__.py](src/core/__init__.py).
- Ações de UI: [src/actions/select2.py](src/actions/select2.py) (Select2), [src/actions/radio.py](src/actions/radio.py) (rádios), reexportados em [src/actions/__init__.py](src/actions/__init__.py).
- Navegação: [src/navigation/flow.py](src/navigation/flow.py) (Nova Consulta, filtros, preparo inicial), reexportado por [src/navigation/__init__.py](src/navigation/__init__.py).
- Scraping: [src/scraping/runner.py](src/scraping/runner.py) (loop principal/CSV), [src/scraping/table.py](src/scraping/table.py) (tabela, Pré-Selecionado, categorias), [src/scraping/extract.py](src/scraping/extract.py) (modal ENEM), reexportados por [src/scraping/__init__.py](src/scraping/__init__.py).
- [requirements.txt](requirements.txt): dependências Python.
- [notas_fies_medicina.csv](notas_fies_medicina.csv): saída gerada/atualizada pelo script.

## Solução de Problemas
- **Chrome/Driver:** `webdriver-manager` baixa o driver automaticamente; garanta que o Google Chrome esteja instalado e atualizado.
- **CAPTCHA constante:** O site pode impor verificações; responda quando solicitado. Se ocorrer com muita frequência, tente executar em horários diferentes ou reduzir o ritmo (desative `FAST_MODE`).
- **Mudanças no site:** Seletores podem quebrar se o layout mudar. Ajuste os seletores no código conforme necessário.
- **Permissões/antivírus:** Alguns antivírus bloqueiam automação de navegador; permita a execução do Python/ChromeDriver.

### Troubleshooting de Timeouts

| Sintoma | Possível Causa | Solução |
|---------|----------------|---------|
| Muitos timeouts no início | Conexão lenta ou site sobrecarregado | Aumente `RETRY_DELAY` para 5s ou mais |
| Timeouts em um estado específico | Muitos municípios/IES nesse estado | Normal; o retry automático deve resolver |
| Taxa de sucesso de retry baixa (<50%) | Site pode estar bloqueando | Desative `FAST_MODE`, aumente delays |
| Todos os retries falham | Possível mudança no site ou bloqueio | Verifique se o site está acessível manualmente |

**Dica:** Se timeouts são frequentes, considere:
1. Desativar `FAST_MODE` em `settings.py`
2. Aumentar `MAX_RETRIES` para 5
3. Executar em horários de menor tráfego (madrugada)

## Avisos
- Respeite os termos de uso do site do FIES e boas práticas de scraping.
- Use este projeto apenas para fins legítimos e educativos.

---
Feito com Selenium + ChromeDriver. Contribuições são bem-vindas.
