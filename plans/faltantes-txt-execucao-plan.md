Problema
- Hoje não existe um modo nativo para executar apenas os itens listados em `notas_fies_medicina_faltantes.txt` (ou versão regular).
- O fluxo atual exige conversão manual para `notas_fies_medicina_falhas.csv`, gerando trabalho extra e risco operacional.

Objetivo
- Permitir execução direta dos faltantes via CLI, com segurança e previsibilidade, respeitando modalidade social/regular.

Abordagem
- Adicionar uma nova flag CLI para informar o arquivo TXT de faltantes e reaproveitar o fluxo de `run_scraper` com `alvos_review`.
- Implementar parser robusto para o formato `UF|Municipio|IES|Codigo`.
- Fazer deduplicação e validação de entrada antes da execução.

Escopo de implementação
1) CLI
- Incluir argumento em `src/app.py`:
  - `--faltantes-txt <caminho>` (aceita caminho customizado).
- Regras:
  - Se informado, executar modo “apenas faltantes”.
  - Compatibilidade com `--modalidade regular` e `--fies-regular`.
  - Evitar conflito de intenção com `--check` (definir precedência clara e log explícito).

2) Leitura do TXT
- Criar helper em `src/scraping/runner.py` para ler TXT:
  - aceitar linhas no padrão `UF|Municipio|IES|Codigo`;
  - ignorar linhas vazias/inválidas com aviso;
  - normalizar campos (`strip`) e deduplicar por `(UF, Municipio, IES ou Codigo)`.

3) Execução dos alvos
- Adicionar função pública `run_faltantes_txt(ctx, caminho_txt, caminho_csv=None)` em `runner.py`.
- Converter linhas válidas para o formato de alvos já aceito por `run_scraper(alvos_review=...)`.
- Se arquivo vazio/sem linhas válidas, encerrar com mensagem clara.
- Remoção progressiva do TXT:
  - conforme um alvo for efetivamente salvo/confirmado no CSV de saída, remover a linha correspondente do TXT de faltantes;
  - persistir atualização do TXT em tempo real (ou em checkpoints curtos) para suportar interrupções sem retrabalho;
  - usar correspondência robusta por `(UF, Município, código IES)` com fallback por nome normalizado.

4) Modalidade e arquivos
- Usar `_caminho_csv_modalidade()` para garantir que a execução grave no CSV correto.
- Se `--faltantes-txt` não receber caminho:
  - social: `notas_fies_medicina_faltantes.txt`
  - regular: `notas_fies_medicina_faltantes_regular.txt`

5) Observabilidade
- Logar no início:
  - arquivo usado,
  - quantidade de linhas lidas,
  - válidas, inválidas e deduplicadas.
- Logar no fim:
  - quantidade de alvos efetivamente enviados ao scraper,
  - quantidade removida do TXT por sucesso,
  - quantidade remanescente no TXT.

6) Documentação
- Atualizar `README.md` com exemplos:
  - `python main.py --faltantes-txt notas_fies_medicina_faltantes.txt`
  - `python main.py --faltantes-txt notas_fies_medicina_faltantes_regular.txt --modalidade regular`
  - `python main.py --faltantes-txt` (usa padrão por modalidade).

Critérios de aceite
- Com `--faltantes-txt`, o sistema processa apenas itens do TXT.
- Funciona em social e regular sem misturar arquivos.
- Linhas inválidas não derrubam execução; são reportadas.
- Ao obter sucesso de um faltante no CSV, o item correspondente é removido do TXT durante a execução.
- Não altera comportamento existente de `--check`, `--review` e modo padrão quando a flag não é usada.
