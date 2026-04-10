# Coletor de Notas FIES — Medicina

Scraper automatizado (Selenium) que percorre os estados e municípios no portal oficial do FIES para coletar informações de cursos de Medicina, salvando resultados continuamente em CSV.

## Visão Geral
- **Navegação automatizada:** Usa Selenium + Chrome para interagir com filtros (Estado, Município, Curso, IES, Conceito).
- **Curso alvo:** Seleção exata de "MEDICINA" (evita confusão com Biomedicina).
- **Categorias:** Coleta notas por categoria (Ampla, PPIQ, PCD) e a nota do último Pré-Selecionado na lista atual.
- **CAPTCHA:** Requer intervenção humana quando solicitado; o script pausa e aguarda confirmação no terminal.
- **Persistência incremental:** Escreve/atualiza o arquivo CSV a cada município processado.
- **Tratamento de timeout/504:** Sistema inteligente de retry que aguarda recuperação da página sem recarregar (preservando sessão e CAPTCHA).
- **Robustez contra StaleElement:** Retry automático para elementos DOM que são re-renderizados durante navegação.
- **Registro de falhas:** IES que falharem após todas as tentativas são registradas em `notas_fies_medicina_falhas.csv` para revisão posterior.

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

### Execução básica
```bash
python main.py
```
Durante a execução:
- Uma janela do Chrome será aberta em [main.py](main.py) e o site do FIES será carregado.
- Quando o CAPTCHA aparecer, o terminal mostrará a mensagem "Resolva o CAPTCHA e pressione ENTER". Resolva-o no navegador e pressione ENTER no terminal para continuar.
- O script iterará por todos os estados e seus municípios, selecionando o curso de Medicina e as IES disponíveis.
- O arquivo de saída [notas_fies_medicina.csv](notas_fies_medicina.csv) é atualizado continuamente (encoding UTF-8 com BOM para fácil abertura no Excel).

### Modalidades FIES
O script suporta coleta para diferentes modalidades do FIES através da flag `--modalidade`:

```bash
# Modalidade Social (padrão)
python main.py

# Modalidade Regular (explícita)
python main.py --modalidade regular

# Atalho para modalidade Regular
python main.py --fies-regular
```

**Diferenças entre modalidades:**
- **Social (padrão):** Salva em `notas_fies_medicina.csv`
- **Regular:** Salva em `notas_fies_medicina_fiesregular.csv`

A modalidade define qual rádio button será selecionado no portal FIES e determina o arquivo CSV de saída.

### Outros modos de execução

```bash
# Modo de checagem (apenas verifica cobertura sem coletar notas)
python main.py --check

# Modo review (executar o fluxo padrão)
python main.py --review

# Executar apenas itens do TXT de faltantes (arquivo padrão da modalidade)
python main.py --faltantes-txt

# Executar apenas itens de um TXT específico
python main.py --faltantes-txt notas_fies_medicina_faltantes.txt

# Executar faltantes da modalidade regular
python main.py --faltantes-txt --modalidade regular
```

### Comportamento em caso de timeout/erro 504
- Quando a API do portal demorar muito ou retornar erro 504, o script **não recarrega a página** (para preservar a sessão e evitar novo CAPTCHA).
- O sistema aguarda automaticamente 15 segundos para a página se recuperar sozinha.
- Se a página não responder, o terminal exibirá uma mensagem pedindo intervenção manual: "Verifique o navegador: pode haver erro 504, CAPTCHA ou tela em branco."
- Resolva o problema no navegador (se necessário) e pressione ENTER para continuar.
- Após 3 tentativas sem sucesso, a IES é registrada em `notas_fies_medicina_falhas.csv` e o script continua com a próxima.

## Saída (CSV)
### Arquivo principal
O arquivo de saída depende da modalidade selecionada:
- **Modalidade Social:** [notas_fies_medicina.csv](notas_fies_medicina.csv) (padrão)
- **Modalidade Regular:** [notas_fies_medicina_fiesregular.csv](notas_fies_medicina_fiesregular.csv)

Colunas:
- **estado:** UF (ex.: SP, RJ)
- **municipio:** Nome do município consultado
- **curso:** "MEDICINA"
- **ies:** Instituição de Ensino Superior
- **conceito_curso:** Conceito listado após seleção da IES
- **nota_ultimo_aprovado:** Nota (texto numérico) da última linha após expandir a listagem
- **nota_enem_ultimo_ampla:** NOTA ENEM do último candidato na categoria Ampla
- **nota_enem_ultimo_ppiq:** NOTA ENEM do último candidato na categoria PPIQ
- **nota_enem_ultimo_pcd:** NOTA ENEM do último candidato na categoria PCD

### Arquivo de falhas: [notas_fies_medicina_falhas.csv](notas_fies_medicina_falhas.csv)

Registra IES que falharam após todas as tentativas de coleta, contendo:
- **estado, municipio, curso, ies, ies_codigo**
- **motivo:** Razão da falha (ex.: `timeout_pesquisa`, `nao_selecionada`)

Observações:
- Notas podem vir vazias quando não encontradas ou quando a navegação encontra limitações da página.
- Valores numéricos podem aparecer com vírgula no site; o script normaliza onde aplicável.

## Configurações Úteis
No início de [src/config/settings.py](src/config/settings.py):
- **`FAST_MODE`**: acelera interações e reduz esperas. Útil para evitar expiração de sessão; se notar instabilidade, defina como `False`.
- **`FIES_MODALIDADE`**: define a modalidade padrão (`"social"` ou `"regular"`). Pode ser sobrescrito pela flag `--modalidade` na linha de comando.

## Dicas de Uso
- Mantenha o Chrome visível para conseguir interagir com CAPTCHAs quando solicitado.
- Evite usar o computador de forma que atrapalhe os cliques automatizados enquanto o script está rodando.
- A coleta completa (todos os estados/municípios) pode demorar. O CSV é atualizado a cada município, permitindo interromper e já aproveitar os dados coletados.

## Melhorias de Robustez

### Sistema de Retry Inteligente para Timeout/504
O scraper implementa um mecanismo robusto de tratamento de erros quando o portal FIES fica lento ou retorna erro 504:

- **Preservação de sessão:** Nunca recarrega a página automaticamente, evitando perda de sessão e novo CAPTCHA.
- **Recuperação automática:** Aguarda até 15 segundos para a página se recuperar sozinha.
- **Intervenção assistida:** Se a página não responder, pausa e solicita verificação manual no terminal.
- **Retry configurável:** Até 3 tentativas antes de registrar falha e continuar.
- **Registro de falhas:** IES problemáticas são salvas em `notas_fies_medicina_falhas.csv` com motivo detalhado.

Implementado em `src/core/retry.py` com as funções:
- `aguardar_pagina_responsiva()`: Verifica se a página saiu do estado de loading
- `com_retry_timeout()`: Wrapper genérico de retry para operações sujeitas a timeout

### Tratamento de StaleElementReferenceException
Elementos DOM que são destruídos e recriados durante navegação (especialmente Select2 de municípios ao trocar de estado) agora têm retry automático:

- Detecta quando um elemento se torna "stale" (referência desatualizada)
- Retenta automaticamente até 3 vezes com intervalo de 0.5s
- Elimina falhas intermitentes causadas por re-renderização do DOM

Implementado em `src/actions/select2.py` na função `listar_opcoes_select2()`.

### Executar apenas alguns estados (opcional)
Edite o dicionário `ESTADOS` em [main.py](main.py) para reduzir o escopo, por exemplo:

```python
ESTADOS = {
    "SP": "São Paulo",
    "RJ": "Rio de Janeiro",
}
```

## Estrutura do Projeto
- [main.py](main.py): ponto de entrada que recebe argumentos CLI e chama a automação.
- [src/app.py](src/app.py): orquestração do fluxo principal e parser de argumentos (--modalidade, --check, --review, --fies-regular).
- Configuração: [src/config/settings.py](src/config/settings.py) (FAST_MODE, FIES_MODALIDADE, BASE_URL, colunas), [src/config/estados.py](src/config/estados.py) (mapa UF → nome), reexportados por [src/config/__init__.py](src/config/__init__.py).
- Núcleo: 
  - [src/core/browser.py](src/core/browser.py) (WebDriver)
  - [src/core/utils.py](src/core/utils.py) (delays/normalização)
  - [src/core/retry.py](src/core/retry.py) (retry inteligente para timeout/504)
  - Reexportados por [src/core/__init__.py](src/core/__init__.py).
- Ações de UI: [src/actions/select2.py](src/actions/select2.py) (Select2 com retry anti-stale), [src/actions/radio.py](src/actions/radio.py) (rádios), reexportados em [src/actions/__init__.py](src/actions/__init__.py).
- Navegação: [src/navigation/flow.py](src/navigation/flow.py) (Nova Consulta, filtros, preparo inicial), reexportado por [src/navigation/__init__.py](src/navigation/__init__.py).
- Scraping: [src/scraping/runner.py](src/scraping/runner.py) (loop principal/CSV), [src/scraping/table.py](src/scraping/table.py) (tabela, Pré-Selecionado, categorias), [src/scraping/extract.py](src/scraping/extract.py) (modal ENEM), reexportados por [src/scraping/__init__.py](src/scraping/__init__.py).
- [requirements.txt](requirements.txt): dependências Python.
- Arquivos de saída:
  - [notas_fies_medicina.csv](notas_fies_medicina.csv): saída para modalidade Social (padrão).
  - [notas_fies_medicina_fiesregular.csv](notas_fies_medicina_fiesregular.csv): saída para modalidade Regular.
  - [notas_fies_medicina_falhas.csv](notas_fies_medicina_falhas.csv): registro de IES que falharam durante coleta.

## Solução de Problemas
- **Chrome/Driver:** `webdriver-manager` baixa o driver automaticamente; garanta que o Google Chrome esteja instalado e atualizado.
- **CAPTCHA constante:** O site pode impor verificações; responda quando solicitado. Se ocorrer com muita frequência, tente executar em horários diferentes ou reduzir o ritmo (desative `FAST_MODE`).
- **Timeout/504 frequente:** O portal pode ficar lento em horários de pico. O script aguarda automaticamente recuperação, mas se persistir, revise `notas_fies_medicina_falhas.csv` e tente novamente mais tarde.
- **StaleElementReferenceException:** Já tratado automaticamente com retry (até 3 tentativas). Se ainda ocorrer, pode indicar mudanças no layout do site.
- **Mudanças no site:** Seletores podem quebrar se o layout mudar. Ajuste os seletores no código conforme necessário.
- **Permissões/antivírus:** Alguns antivírus bloqueiam automação de navegador; permita a execução do Python/ChromeDriver.

## Avisos
- Respeite os termos de uso do site do FIES e boas práticas de scraping.
- Use este projeto apenas para fins legítimos e educativos.

---
Feito com Selenium + ChromeDriver. Contribuições são bem-vindas.
