# Coletor de Notas FIES — Medicina

Scraper automatizado (Selenium) que percorre os estados e municípios no portal oficial do FIES para coletar informações de cursos de Medicina, salvando resultados continuamente em CSV.

## Visão Geral
- **Navegação automatizada:** Usa Selenium + Chrome para interagir com filtros (Estado, Município, Curso, IES, Conceito).
- **Curso alvo:** Seleção exata de "MEDICINA" (evita confusão com Biomedicina).
- **Categorias:** Coleta notas por categoria (Ampla, PPIQ, PCD) e a nota do último aprovado na lista atual.
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
- [main.py](main.py): script principal do scraper.
- [requirements.txt](requirements.txt): dependências Python.
- [notas_fies_medicina.csv](notas_fies_medicina.csv): saída gerada/atualizada pelo script.

## Solução de Problemas
- **Chrome/Driver:** `webdriver-manager` baixa o driver automaticamente; garanta que o Google Chrome esteja instalado e atualizado.
- **CAPTCHA constante:** O site pode impor verificações; responda quando solicitado. Se ocorrer com muita frequência, tente executar em horários diferentes ou reduzir o ritmo (desative `FAST_MODE`).
- **Mudanças no site:** Seletores podem quebrar se o layout mudar. Ajuste os seletores no código conforme necessário.
- **Permissões/antivírus:** Alguns antivírus bloqueiam automação de navegador; permita a execução do Python/ChromeDriver.

## Avisos
- Respeite os termos de uso do site do FIES e boas práticas de scraping.
- Use este projeto apenas para fins legítimos e educativos.

---
Feito com Selenium + ChromeDriver. Contribuições são bem-vindas.
