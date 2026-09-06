# Auditoria completa da automação FIES

**Data da auditoria:** 4 de setembro de 2026  
**Runtime auditado:** Windows, Python 3.14.5, Selenium 4.48.0, webdriver-manager 4.1.2, Pandas 3.0.5, Chrome 152.0.7977.76 e ChromeDriver 152.0.7977.82  
**Escopo:** modalidades Social e Regular; modos normal, `--check`, `--review` e `--faltantes-txt`; persistência, retomada, tratamento de falhas, bootstrap do navegador, contratos CLI, dados existentes e smoke test controlado.  
**Regra observada:** nenhum CSV/TXT oficial foi alterado e nenhuma coleta nacional foi iniciada.

## Parecer executivo

**Parecer: não liberar uma nova execução nacional antes de corrigir os itens P0 e validar novamente o fluxo real.**

Foram classificados **23 achados**:

- **4 P0:** bloqueio ou risco imediato de término falso/dado incorreto em escala nacional;
- **10 P1:** perda de cobertura, mistura de modalidade, corrupção/omissão de dados ou quebra de retomada;
- **7 P2:** contratos operacionais incorretos, observabilidade insuficiente e riscos ambientais;
- **2 P3:** dívida interna e manutenção.

Os maiores riscos são:

1. o programa falha no console Windows auditado ao imprimir o primeiro emoji;
2. uma exceção arbitrária no município é engolida e a execução ainda imprime `FINALIZADO`;
3. a troca de categoria pode retornar sucesso sem trocar a categoria, permitindo gravar a mesma origem como Ampla, PPIQ e PCD;
4. a retomada presume que o CSV seja um prefixo ordenado, premissa que os dois CSVs atuais não satisfazem;
5. escrita e reescrita dos artefatos não são atômicas nem protegidas contra outra instância/Excel;
6. o `--check` não encontra conceitos vazios lidos como `NaN` e, no Regular atual, retorna zero alvos apesar das duas linhas truncadas.

O smoke test real chegou ao portal e confirmou que o alvo `AC / CRUZEIRO DO SUL / MEDICINA / AFYA ... (24547) / conceito 5` existe. A navegação manual controlada conseguiu montar os filtros em Social e Regular. O mesmo pré-fluxo executado pelas funções Selenium do projeto falhou antes da pesquisa: em Social, `aplicar_filtros()` retornou `False`; em Regular, a segunda navegação expirou esperando o DOM. O reCAPTCHA estava ativo e não foi marcado. Portanto, as três categorias não puderam ser validadas de ponta a ponta sem mascarar a falha anterior.

## Método e evidências reproduzíveis

Foram usados:

- leitura integral do código, README, planos, requisitos e artefatos;
- busca de `except`, `pass`, `continue`, retornos vazios, `input()`, leituras e escritas;
- compilação com `python -m compileall -q main.py src`;
- testes unitários temporários com dublês, sem arquivos permanentes;
- CSVs/TXTs temporários para truncamento, `NaN`, duplicação, caminho customizado e bloqueio de arquivo;
- abertura e fechamento real do Chrome pelo `build_browser()`;
- navegação real, sem pesquisa e sem persistência, até o bloqueio do reCAPTCHA;
- hashes SHA-256 antes e depois;
- mapa estrutural auxiliar do repositório.

O mapa estrutural encontrou 156 nós, 409 arestas e 8 comunidades, destacando `BrowserContext`, `buscar_notas_por_municipio()`, `run_checker()` e `run_scraper()` como pontos de maior acoplamento. O diagnóstico do mapa também apontou **69 arestas com endpoint pendente** e **23 relações colapsadas no grafo não direcionado**; por isso, nenhum achado abaixo depende exclusivamente dessas relações inferidas.

### Comandos-base

```powershell
python -m compileall -q main.py src
python main.py --help
python -c "import sys,pandas,selenium,webdriver_manager; print(sys.version); print(pandas.__version__, selenium.__version__, webdriver_manager.__version__)"
```

### Integridade dos artefatos oficiais

| Arquivo | Bytes | SHA-256 antes | SHA-256 depois | Resultado |
|---|---:|---|---|---|
| `notas_fies_medicina.csv` | 21264 | `09251AB08E33E344B4A2B4FC968D4BE5D31F7AF42BBA3006440169206F2499E1` | igual | intacto |
| `notas_fies_medicina_fiesregular.csv` | 21673 | `A748638555B506F465632A1542F074B8BEB6D4BA7E1D6B236AD6651E70224FF7` | igual | intacto |
| `notas_fies_medicina_falhas.csv` | 145 | `79A3749CE77C221A3C6DCA11A5FB059B06140A389DAC20A765AEFB88805D264F` | igual | intacto |
| `notas_fies_medicina_faltantes.txt` | 601 | `725047AEA92C9E83F7C8B7FFC27E32538417A008910BE669CFA154FEEF43BB4F` | igual | intacto |
| `notas_fies_medicina_faltantes_regular.txt` | 69 | `196F10E5B37E313DABE968994BA766CDB3BF11567BDE3908939A3306358F6EFB` | igual | intacto |

## Smoke test controlado

### Bootstrap

- `ChromeDriverManager().install()` resolveu o driver em cache/gerenciado com sucesso.
- `build_browser()` abriu e fechou o Chrome corretamente.
- Capacidades observadas: navegador `152.0.7977.76`, driver `152.0.7977.82`, `pageLoadStrategy=none`.
- Em uma abertura real do Selenium, após 8 segundos, a página estava com `document.readyState == "complete"`, o seletor de Estado existia, não havia marcador Cloudflare visível e havia dois frames reCAPTCHA.
- Cloudflare deve ser tratado como risco intermitente: a evidência inicial do plano registrou desafio ativo, mas ele não apareceu nesta amostra. O reCAPTCHA permaneceu confirmado.

### Alvo e transições

Na inspeção controlada do portal:

- Estado: `ACRE - AC`;
- municípios oferecidos: `CRUZEIRO DO SUL` e `RIO BRANCO`;
- cursos em Cruzeiro do Sul: `ENFERMAGEM` e `MEDICINA`;
- IES: `AFYA FACULDADE DE CIÊNCIAS MÉDICAS DE CRUZEIRO DO SUL (24547)`;
- conceito: `5`;
- rádio Social e rádio Regular puderam ser selecionados, com a propriedade DOM `checked` alternando corretamente;
- o atributo HTML `checked` permaneceu ausente, evidência direta contra os XPaths que procuram `@checked`.

Na execução das funções do projeto, após aguardar explicitamente o DOM:

```text
Social: dom_ready=true, radio_social=true, aplicar_filtros=false, ies_count=0
Regular: TimeoutException esperando os controles após a segunda navegação
```

O teste parou antes de `Pesquisar`. Não houve clique no reCAPTCHA, leitura de categorias, abertura de modal ou gravação de resultado. Isso é uma limitação do smoke test, mas também um resultado operacional: o caminho automatizado falhou antes do CAPTCHA em um alvo que estava disponível pela navegação controlada.

## Achados P0

### P0-01 — Logs com emoji derrubam o runtime Windows auditado

- **Estado:** confirmado.
- **Evidência:** `sys.stdout.encoding`, `sys.stderr.encoding` e `locale.getpreferredencoding(False)` retornaram `cp1252`; `PYTHONUTF8` e `PYTHONIOENCODING` estavam ausentes. A primeira chamada que imprimiu `📄` gerou `UnicodeEncodeError`. Há emojis desde [src/app.py](src/app.py#L51), [src/navigation/flow.py](src/navigation/flow.py#L24) e por todo [src/scraping/runner.py](src/scraping/runner.py).
- **Cenário:** executar `python main.py --modalidade regular` ou chegar ao primeiro aviso em um PowerShell/console CP1252.
- **Tipo:** interrupção explícita antes ou durante a coleta.
- **Impacto/alcance:** todos os modos e modalidades no runtime oficial auditado, salvo configuração externa de UTF-8.
- **Correção mínima:** remover caracteres fora do encoding do console ou centralizar logs com fallback `errors="replace"`; não depender de variável externa não documentada.
- **Regressão:** iniciar cada modo em subprocesso com stdout CP1252 e exigir saída/encerramento sem `UnicodeEncodeError`.

### P0-02 — Exceção arbitrária vira término falso com `FINALIZADO`

- **Estado:** confirmado por dublê.
- **Evidência:** [src/scraping/runner.py](src/scraping/runner.py#L803) envolve todo `buscar_notas_por_municipio()` em `except Exception`, não registra a exceção e segue até [src/scraping/runner.py](src/scraping/runner.py#L840). O teste injetou `RuntimeError("boom")`: nada foi propagado ou logado e a saída continha `FINALIZADO`.
- **Cenário:** falha de escrita, seletor inesperado, stale não tratado, erro de callback ou defeito interno em qualquer município.
- **Tipo:** falha silenciosa e falso sucesso.
- **Impacto/alcance:** modo normal, `--review` e `--faltantes-txt`; pode deixar o navegador numa página de resultado e provocar falhas em cascata nos municípios seguintes.
- **Correção mínima:** capturar somente erros esperados, registrar contexto/traceback, marcar execução incompleta e retornar status não zero; erro de persistência nunca deve ser convertido em “seguir”.
- **Regressão:** injetar exceção em seleção, pesquisa, extração e escrita; exigir erro visível, ausência de `FINALIZADO` e artefato de falha.

### P0-03 — Categoria pode retornar sucesso sem mudar a tabela

- **Estado:** confirmado por dublê; risco de dado incorreto confirmado estruturalmente.
- **Evidência:** [src/scraping/table.py](src/scraping/table.py#L152) compara somente a quantidade de linhas; se a quantidade não muda em 8 segundos, ignora o timeout e retorna `True` em [src/scraping/table.py](src/scraping/table.py#L197). O teste simulou clique sem alteração e obteve `True`. O loop em [src/scraping/runner.py](src/scraping/runner.py#L505) aceita isso e lê a linha corrente para Ampla, PPIQ e PCD.
- **Cenário:** duas categorias têm a mesma quantidade de candidatos, a requisição falha ou o clique não troca a aba.
- **Tipo:** falso sucesso e associação da nota à categoria errada.
- **Impacto/alcance:** todos os modos que coletam notas; pode duplicar uma categoria nas três colunas sem sinal externo.
- **Correção mínima:** verificar estado ativo/código da categoria e uma identidade da resposta/tabela, não contagem; falhar se a origem não mudar.
- **Regressão:** tabelas de mesmo tamanho com conteúdos diferentes; clique inócuo deve retornar `False`; cada coluna deve carregar identificador da categoria que a originou.

### P0-04 — Retomada por última linha é incompatível com os CSVs atuais

- **Estado:** confirmado nos dados e em simulação.
- **Evidência:** [src/scraping/runner.py](src/scraping/runner.py#L572) usa o último `(UF, município)` e [src/scraping/runner.py](src/scraping/runner.py#L734) pula tudo antes dele; qualquer município com uma linha é considerado processado. A lista do portal é ordenada por `sorted()` em [src/actions/select2.py](src/actions/select2.py#L202). Foram encontradas 8 inversões de ordem no Social e 3 no Regular. As últimas linhas são `SP/FERNANDÓPOLIS` e `SP/PRESIDENTE PRUDENTE`, embora existam backfills de UFs/municípios anteriores no corpo.
- **Cenário:** CSV fora de ordem, backfill manual, município parcialmente salvo que não é a última linha, ou linha final truncada.
- **Tipo:** omissão silenciosa de cobertura.
- **Impacto/alcance:** modo normal; uma execução pode pular faltantes legítimos em quase todo o país e ainda finalizar.
- **Correção mínima:** abandonar cursor por última linha; calcular trabalho por chave `(modalidade, UF, município, IES/código)` e completar cada conjunto esperado. Validar o CSV antes de iniciar.
- **Regressão:** CSV embaralhado, backfill, município parcial no meio e linha final truncada devem produzir o mesmo conjunto de pendências que um CSV ordenado.

## Achados P1

### P1-01 — Seleção de modalidade pode reportar sucesso sem rádio selecionado

- **Estado:** confirmado por dublê e pelo DOM real.
- **Evidência:** [src/actions/radio.py](src/actions/radio.py#L10) ignora timeout de `is_selected()` e retorna `True`; os fallbacks também não verificam o estado. Social/Regular procuram `@checked` em [src/actions/radio.py](src/actions/radio.py#L70) e [src/actions/radio.py](src/actions/radio.py#L107), mas no portal a propriedade `checked` mudou e o atributo continuou ausente.
- **Cenário:** clique interceptado, DOM refeito ou rótulo genérico `Fies` casar primeiro com `Fies Social`.
- **Tipo:** falso sucesso e possível mistura de modalidade.
- **Impacto/alcance:** todos os modos; dados Social podem ser gravados no CSV Regular ou vice-versa.
- **Correção mínima:** selecionar pelo `id/value` e exigir `element.is_selected()`/propriedade JS após cada tentativa.
- **Regressão:** clique sem efeito deve retornar `False`; Social exige `stCadunicoS`, Regular exige `stCadunicoN`.

### P1-02 — Select2 não valida Estado/Município e pode aceitar IES errada

- **Estado:** confirmado estruturalmente; o smoke Selenium retornou `aplicar_filtros=false` apesar do alvo existir.
- **Evidência:** `select2()` em [src/actions/select2.py](src/actions/select2.py#L36) digita e pressiona Enter sem verificar o valor final. `select2_exact_multi()` em [src/actions/select2.py](src/actions/select2.py#L309) pode escolher o primeiro item válido quando não acha o alvo e valida o texto do próprio candidato, não o texto pedido. `run_checker()` usa esse retorno em [src/scraping/runner.py](src/scraping/runner.py#L1134) sem conferir a IES esperada.
- **Cenário:** AJAX ainda carregando, busca aproximada, nomes parecidos ou opção-alvo ausente.
- **Tipo:** seleção ausente/errada e gravação no registro errado.
- **Impacto/alcance:** todos os fluxos de filtros; `--check` pode atribuir conceito de uma IES a outra.
- **Correção mínima:** toda seleção deve receber valor esperado e validar texto/código final; remover fallback para “primeira opção” quando existe alvo explícito.
- **Regressão:** alvo ausente nunca seleciona outro; valores pós-clique devem coincidir em Estado, Município, Curso, IES e Conceito.

### P1-03 — Persistência não é atômica, não tem lock e falha de escrita pode sumir

- **Estado:** confirmado parcialmente; riscos de interrupção/concorrência são determinísticos pelo desenho.
- **Evidência:** [src/scraping/runner.py](src/scraping/runner.py#L126) faz append direto; [src/scraping/runner.py](src/scraping/runner.py#L135) reescreve o CSV inteiro; [src/scraping/runner.py](src/scraping/runner.py#L712) sobrescreve o TXT diretamente. Não há arquivo temporário, `fsync`, `os.replace` ou lock. Um lock exclusivo de faixa no Windows produziu `PermissionError`; no fluxo normal esse erro alcança o `except Exception` silencioso do P0-02.
- **Cenário:** Excel aberto, duas instâncias, queda durante append/reescrita ou disco indisponível.
- **Tipo:** perda, truncamento, duplicação ou falso sucesso.
- **Impacto/alcance:** CSVs principais, CSV de falhas e TXTs.
- **Correção mínima:** lock por artefato; escrita completa em temporário no mesmo diretório, flush/fsync e `os.replace`; abortar em erro.
- **Regressão:** arquivo bloqueado, queda antes do replace e duas instâncias; o original deve permanecer íntegro e a segunda instância deve falhar claramente.

### P1-04 — `NaN` impede o `--check` de detectar conceito vazio

- **Estado:** confirmado em temporário e nos arquivos reais.
- **Evidência:** [src/scraping/runner.py](src/scraping/runner.py#L912) faz `str(row.get(...)).strip()`; `NaN` vira a string truthy `"nan"` e é ignorado. Um CSV temporário com conceito vazio retornou zero nomes/códigos/municípios. Nos arquivos atuais, o helper retornou zero alvos para ambos; o Regular tem duas linhas com conceito ausente.
- **Cenário:** campo CSV vazio lido pelo Pandas como `NaN`.
- **Tipo:** falso negativo e escopo errado do `--check`.
- **Impacto/alcance:** Social e Regular; pode disparar varredura nacional em vez do reparo focal ou declarar ausência de trabalho.
- **Correção mínima:** usar `pd.isna()`/string nullable e validar esquema antes do loop; não engolir erro de leitura em [src/scraping/runner.py](src/scraping/runner.py#L929).
- **Regressão:** `""`, `NaN`, espaços e coluna ausente devem ser classificados explicitamente.

### P1-05 — Códigos válidos de IES com 2 ou 3 dígitos são ignorados

- **Estado:** confirmado nos CSVs.
- **Evidência:** `_IES_CODIGO_RE` exige 4+ dígitos em [src/scraping/runner.py](src/scraping/runner.py#L37), assim como [src/actions/select2.py](src/actions/select2.py#L282). O Social contém 3 códigos de 2 dígitos e 64 de 3 dígitos; o Regular contém 3 e 68. Exemplos válidos: `(30)`, `(68)`, `(319)`, `(449)` e `(621)`.
- **Cenário:** matching, deduplicação ou remoção de faltante por código curto.
- **Tipo:** identidade incompleta e falso não-casamento.
- **Impacto/alcance:** progresso, `--check`, `--review`, `--faltantes-txt` e arquivo de falhas.
- **Correção mínima:** aceitar `\d+` dentro do sufixo e validar o valor separadamente.
- **Regressão:** códigos de 1 a 5 dígitos, com matching por código mesmo quando o nome muda.

### P1-06 — `--faltantes-txt` não é idempotente nem progressivo em caso de interrupção

- **Estado:** confirmado por simulação e fluxo de chamadas.
- **Evidência:** duplicatas exatas são ignoradas antes de registrar todos os índices em [src/scraping/runner.py](src/scraping/runner.py#L691); após remover o índice 0, a linha duplicada permaneceu. O CSV é salvo dentro de `buscar_notas_por_municipio()`, mas o callback que remove o TXT só é chamado depois que a função retorna, em [src/scraping/runner.py](src/scraping/runner.py#L803). Se houver queda após salvar uma IES e antes do retorno, a próxima execução pula a IES já existente e nunca chama o callback. A rotina ainda marca índices como removidos antes de confirmar a escrita do TXT em [src/scraping/runner.py](src/scraping/runner.py#L883).
- **Cenário:** duplicata, queda no meio do município ou falha ao sobrescrever TXT.
- **Tipo:** pendência fantasma e retrabalho permanente.
- **Impacto/alcance:** Social e Regular em `--faltantes-txt`.
- **Correção mínima:** reconciliar TXT com CSV no início; chamar confirmação imediatamente após commit atômico de cada registro; mapear todos os índices duplicados; só atualizar estado em memória após persistir.
- **Regressão:** duplicata exata, queda após primeira IES e falha de escrita; reinício deve convergir para TXT correto.

### P1-07 — Caminho CSV customizado é ignorado e `--review` usa falhas compartilhadas

- **Estado:** confirmado por monkeypatch.
- **Evidência:** `run_faltantes_txt(..., caminho_csv=...)` e `run_review(..., caminho_csv=...)` calculam o caminho, mas chamam `run_scraper()` sem repassá-lo em [src/scraping/runner.py](src/scraping/runner.py#L843) e [src/scraping/runner.py](src/scraping/runner.py#L1212). O teste registrou `False` para ambos os repasses. O CSV de falhas padrão é único em [src/scraping/runner.py](src/scraping/runner.py#L152) e [src/scraping/runner.py](src/scraping/runner.py#L1215), sem campo modalidade.
- **Cenário:** teste seguro em arquivo temporário, review Regular ou chamada programática com destino customizado.
- **Tipo:** escrita no arquivo errado e mistura de escopo.
- **Impacto/alcance:** `--review` e `--faltantes-txt`; uma falha Social pode virar alvo Regular.
- **Correção mínima:** repassar explicitamente o caminho; separar falhas por modalidade ou adicionar modalidade à chave/esquema; remover a linha de falha após sucesso confirmado.
- **Regressão:** destinos sentinela distintos e falhas homônimas em Social/Regular nunca podem cruzar.

### P1-08 — Duas linhas truncadas no CSV Regular são aceitas como progresso

- **Estado:** confirmado.
- **Evidência:** [notas_fies_medicina_fiesregular.csv](notas_fies_medicina_fiesregular.csv#L170) contém `RS,SÃO SEBASTIÃO DO CAÍ,` e [notas_fies_medicina_fiesregular.csv](notas_fies_medicina_fiesregular.csv#L178) contém `SC,CAPIVARI DE BAIXO,`. Cada linha tem 3 de 8 campos. Pandas completa o restante com `NaN`; `carregar_progresso()` preenche com vazio e inclui os municípios em `ja_processados`.
- **Cenário:** executar modo normal ou `--check` sobre o Regular atual.
- **Tipo:** corrupção de esquema tratada como sucesso/progresso.
- **Impacto/alcance:** os municípios podem ser pulados; o `--check` não detecta os conceitos pelo P1-04.
- **Correção mínima:** validação CSV prévia obrigatória e quarentena/aborto ao encontrar largura ou campos-chave inválidos.
- **Regressão:** linha com menos/mais colunas deve impedir execução mutável e informar linha física.

### P1-09 — Seletores globais de tabela/modal não comprovam a origem do dado

- **Estado:** risco confirmado pelo código; validação dinâmica das categorias ficou bloqueada antes da pesquisa.
- **Evidência:** [src/scraping/table.py](src/scraping/table.py#L14) aceita linhas de `//table/tbody/tr` de qualquer tabela e inclui `//tr`, potencialmente cabeçalho. [src/scraping/extract.py](src/scraping/extract.py#L14) procura qualquer `NOTA ENEM` visível; falha de fechamento/invisibilidade do modal é ignorada. `extrair_nota_enem_de_linha()` converte qualquer exceção em `None` em [src/scraping/extract.py](src/scraping/extract.py#L70).
- **Cenário:** modal anterior permanece, tabela auxiliar aparece, cabeçalho é a última linha ou DOM muda.
- **Tipo:** nota de origem errada ou ausência silenciosa.
- **Impacto/alcance:** todas as coletas de notas.
- **Correção mínima:** escopar ao `#listaResultadoConsulta`, excluir cabeçalhos, vincular modal ao botão clicado/categoria e exigir fechamento antes de continuar.
- **Regressão:** duas tabelas e dois modais no DOM; somente a origem correta pode ser aceita.

### P1-10 — Prontidão de página, CAPTCHA e retry não distinguem sessão funcional

- **Estado:** confirmado parcialmente no smoke.
- **Evidência:** [src/navigation/flow.py](src/navigation/flow.py#L20) chama `input()` e depois ignora timeout do seletor; [src/navigation/flow.py](src/navigation/flow.py#L32) repete o padrão em toda “Nova Consulta”. `aguardar_pagina_responsiva()` em [src/core/retry.py](src/core/retry.py#L14) considera apenas `document.readyState == "complete"`, que também ocorre em erro 504/Cloudflare. O `input()` em [src/core/retry.py](src/core/retry.py#L79) pode bloquear execução sem terminal interativo. No smoke, o alvo existia manualmente, mas o fluxo Selenium retornou `False`/timeout antes da pesquisa.
- **Cenário:** usuário pressiona Enter cedo, página completa mas controles ausentes, sessão expirada, 504 ou execução agendada.
- **Tipo:** travamento, falso “página recuperada” ou varredura vazia.
- **Impacto/alcance:** todos os modos; “Nova Consulta” pode exigir intervenção a cada IES.
- **Correção mínima:** máquina de estados explícita: desafio, formulário pronto, resultados, sessão expirada e erro; validar o estado após intervenção e abortar quando inválido.
- **Regressão:** páginas sintéticas para 504, Cloudflare, formulário, resultados e sessão expirada; nenhum estado pode ser confundido com outro.

## Achados P2

### P2-01 — Flags conflitantes são aceitas por precedência implícita

- **Estado:** confirmado.
- **Evidência:** [src/app.py](src/app.py#L11) não usa grupos mutuamente exclusivos. O teste com `--check --review --faltantes-txt x.txt --modalidade social --fies-regular` abriu o browser e executou somente faltantes em Regular. A precedência efetiva é `faltantes > review > check > normal`, e `--fies-regular > --modalidade`.
- **Impacto:** o operador pode executar e gravar um modo/modalidade diferente do solicitado. O browser também é criado antes de validar arquivo ausente/vazio ou CSV de falhas sem alvos.
- **Correção mínima:** conflito deve ser erro de parser; resolver/validar alvos antes do browser; imprimir configuração efetiva.
- **Regressão:** todas as combinações inválidas devem sair não zero sem abrir Chrome.

### P2-02 — `--check` é descrito como checagem, mas altera CSV/TXT

- **Estado:** confirmado pelo código/documentação.
- **Evidência:** o help diz “apenas checagem ... sem pesquisar notas” em [src/app.py](src/app.py#L14), mas [src/scraping/runner.py](src/scraping/runner.py#L1147) altera `conceito_curso`, [src/scraping/runner.py](src/scraping/runner.py#L1158) anexa TXT e [src/scraping/runner.py](src/scraping/runner.py#L1191) reescreve o CSV inteiro.
- **Impacto:** operador pode modificar artefatos oficiais acreditando em modo somente leitura; reserialização amplia o risco do P1-03.
- **Correção mínima:** renomear/documentar como reparo mutável ou separar `--check` somente leitura de um `--repair` explícito.
- **Regressão:** hashes imutáveis em check; mutação somente no modo explicitamente autorizado.

### P2-03 — Normalização decimal corrompe entrada já decimal com ponto

- **Estado:** confirmado em teste de função; dependente do formato momentâneo do portal.
- **Evidência:** [src/core/utils.py](src/core/utils.py#L18) remove todos os pontos antes de trocar vírgula. Resultados: `785,36 -> 785.36`, `1.234,56 -> 1234.56`, mas `785.36 -> 78536`. Não há validação de faixa antes de salvar.
- **Impacto:** uma mudança do portal para ponto decimal produz nota fora de escala.
- **Correção mínima:** detectar formato e validar número em `[0, 1000]` antes do commit.
- **Regressão:** formatos PT-BR, decimal com ponto, espaços, vazio e texto inválido.

### P2-04 — README diverge do comportamento e da versão mínima real

- **Estado:** confirmado.
- **Evidências:** [README.md](README.md#L78) chama `--review` de fluxo padrão, mas ele restringe ao CSV de falhas; [README.md](README.md#L104) lista `nota_ultimo_aprovado`, coluna inexistente; [README.md](README.md#L159) manda editar `ESTADOS` em `main.py`, mas está em `src/config/estados.py`; [README.md](README.md#L16) promete Python 3.9+, embora o código use `str | None`, sintaxe de Python 3.10+; persistência é descrita por município, mas ocorre por IES.
- **Impacto:** operação e recuperação incorretas.
- **Correção mínima:** alinhar README/help aos contratos efetivos após as correções.
- **Regressão:** teste documental simples comparando flags, colunas e arquivos com constantes/parser.

### P2-05 — CSV de falhas pode ser reescrito ou ter linhas descartadas ao ser lido

- **Estado:** confirmado pelo código.
- **Evidência:** [src/scraping/runner.py](src/scraping/runner.py#L143) reindexa e reescreve o arquivo ao detectar cabeçalho diferente; [src/scraping/runner.py](src/scraping/runner.py#L170) faz correção regex destrutiva; [src/scraping/runner.py](src/scraping/runner.py#L620) cai para `on_bad_lines="skip"` sem enumerar perdas.
- **Impacto:** a própria tentativa de review pode apagar campos/linhas de diagnóstico.
- **Correção mínima:** parser somente leitura, relatório de linhas inválidas e reparo explícito/atômico em arquivo separado.
- **Regressão:** CSV com coluna extra, aspas, linha concatenada e linha inválida; nenhuma entrada pode sumir sem contagem/arquivo de quarentena.

### P2-06 — Bootstrap depende de rede/cache e dependências não são reproduzíveis

- **Estado:** risco estrutural; ambiente atual funcional.
- **Evidência:** [requirements.txt](requirements.txt) usa apenas limites inferiores; [src/core/browser.py](src/core/browser.py#L26) chama `ChromeDriverManager().install()` a cada inicialização, sem driver configurável ou fallback explícito. O driver atual foi resolvido e é compatível pela versão principal 152.
- **Impacto:** atualização futura de Selenium/Pandas/Chrome ou indisponibilidade de rede/cache pode quebrar produção sem mudança no repositório.
- **Correção mínima:** registrar versões validadas, permitir caminho de driver/cache e diagnosticar offline antes de abrir o fluxo.
- **Regressão:** bootstrap online, cache offline válido, cache ausente e incompatibilidade de versão.

### P2-07 — `pwsh.exe` rastreado é um shim não assinado e fora do escopo da aplicação

- **Estado:** confirmado.
- **Evidência:** `Get-AuthenticodeSignature` retornou `NotSigned`; SHA-256 `E08ACF6ED91EAE53BEA0E5570DBB9D41E00CFB192C0274B5DB21E5FF6A6FF59D`. [pwsh_stub.cs](pwsh_stub.cs#L7) registra argumentos em `C:\Projetos\teste\pwsh_log.txt`, responde versão fixa `7.0.0` e concatena argumentos ao delegar para `powershell.exe`.
- **Impacto:** invocar `pwsh` a partir do diretório pode executar um binário inesperado, registrar comandos em outro projeto e alterar quoting.
- **Correção mínima:** remover do repositório produtivo ou documentar/renomear como fixture de teste, nunca como `pwsh.exe`.
- **Regressão:** nenhum executável auxiliar genérico deve sombrear ferramentas do sistema.

## Achados P3

### P3-01 — Código morto e telemetria enganosa ampliam a superfície de auditoria

- **Estado:** confirmado.
- **Evidência:** `_selecionar_ies_para_review()` e `_coletar_notas_ies_review()` não têm chamadores; `dados_finais` é acumulado e nunca usado; `novos` e `novos_para_mun` no `--check` permanecem zero; `_limpar_marcas_concorrencia()` não é chamada.
- **Impacto:** manutenção confusa e logs que sugerem métricas não implementadas.
- **Correção mínima:** remover ou conectar explicitamente; calcular métricas reais.
- **Regressão:** análise de símbolos não referenciados e testes das métricas finais.

### P3-02 — Modalidade é estado global mutável

- **Estado:** confirmado.
- **Evidência:** [src/app.py](src/app.py#L43) altera `settings.FIES_MODALIDADE`, consumido por diversos módulos.
- **Impacto:** chamadas embutidas, testes no mesmo processo ou execução concorrente podem herdar modalidade anterior.
- **Correção mínima:** colocar modalidade/caminhos no contexto/configuração imutável passada às funções.
- **Regressão:** Social e Regular no mesmo processo devem permanecer isolados.

## Auditoria dos dados existentes

| Verificação | Social | Regular |
|---|---:|---:|
| Linhas de dados | 241 | 246 |
| Colunas esperadas | 8/8 | 8/8 no header |
| Linhas com largura inválida | 0 | 2 (linhas 170 e 178) |
| Duplicatas completas | 0 | 0 |
| Duplicatas por UF/município/curso/IES | 0 | 0 |
| Conceito ausente pelo Pandas | 0 | 2 |
| Nota Ampla ausente | 21 | 31 |
| Nota PPIQ ausente | 6 | 10 |
| Nota PCD ausente | 57 | 47 |
| Notas não numéricas | 0 | 0 |
| Notas fora de 0–1000 | 0 | 0 |
| Inversões de ordem relevantes à retomada | 8 | 3 |

Faixas observadas:

- Social: Ampla `505.96–785.36`, PPIQ `472.20–761.58`, PCD `468.08–735.06`;
- Regular: Ampla `482.28–825.00`, PPIQ `483.12–790.24`, PCD `501.20–770.38`.

Todos os nomes de IES não truncados terminam com código numérico, mas 67 registros Social e 71 registros Regular usam código com menos de 4 dígitos e são ignorados pelo regex atual. Não foram detectados UF inválido, curso diferente de Medicina ou duplicata de chave.

## Matriz modo × modalidade

| Modo | Social | Regular | Escritas e risco principal |
|---|---|---|---|
| Normal | usa `notas_fies_medicina.csv` | usa `notas_fies_medicina_fiesregular.csv` | append por IES; falhas vão para CSV compartilhado; retomada inválida e término falso |
| `--check` | CSV Social + TXT Social | CSV Regular + TXT Regular | pode alterar conceito, reescrever CSV e anexar TXT; `NaN` elimina alvos |
| `--review` | lê falhas compartilhadas e grava Social | lê as mesmas falhas e grava Regular | não é alias do normal; mistura modalidade; caminho customizado ignorado |
| `--faltantes-txt` | TXT/CSV Social por padrão | TXT/CSV Regular por padrão | remoção atrasada/não atômica; duplicata permanece; caminho CSV customizado ignorado |

Precedência efetiva atual:

```text
modo: --faltantes-txt > --review > --check > normal
modalidade: --fies-regular > --modalidade > settings.FIES_MODALIDADE
```

Essa precedência não é validada nem apresentada de forma suficiente ao operador.

## Plano de correção ordenado por risco

### Fase 0 — Congelar a operação

1. Não executar coleta nacional nem `--check` mutável nos arquivos oficiais.
2. Fazer cópia externa dos cinco artefatos e registrar hashes.
3. Remover/neutralizar o bloqueio CP1252 para permitir testes confiáveis.

### Fase 1 — Eliminar falsos sucessos

1. Propagar erros e status de execução; `FINALIZADO` somente com critérios mensuráveis.
2. Verificar rádio, cada Select2, categoria ativa, origem da tabela e modal.
3. Criar estados explícitos de página/sessão/CAPTCHA/504.
4. Validar nota e categoria antes de qualquer commit.

### Fase 2 — Tornar persistência e retomada seguras

1. Escrita atômica e lock para CSV/TXT/falhas.
2. Validação rígida de esquema/linhas antes de iniciar.
3. Retomada por conjunto de chaves, não última linha.
4. Separar falhas por modalidade e aceitar códigos de qualquer quantidade de dígitos.
5. Reconciliar faltantes com CSV no início e após cada commit.

### Fase 3 — Corrigir contratos

1. Separar check somente leitura de repair mutável.
2. Tornar flags exclusivas e validar antes do browser.
3. Repassar caminhos customizados.
4. Corrigir README/help e registrar versões testadas.
5. Remover `pwsh.exe`/código morto ou isolá-los como fixtures inequívocas.

## Testes de regressão recomendados

Sem exigir framework novo, a correção deve cobrir no mínimo:

1. subprocesso Windows CP1252 para todos os modos;
2. rádio clicado sem alteração;
3. Select2 com alvo ausente, nomes parecidos e AJAX atrasado;
4. categorias de mesmo tamanho e clique sem troca;
5. duas tabelas/dois modais no DOM;
6. CSV truncado, corrompido, vazio, embaralhado e município parcial no meio;
7. arquivo bloqueado e duas instâncias;
8. conceito `NaN`, vazio, espaços e coluna ausente;
9. códigos IES de 1, 2, 3, 4 e 5 dígitos;
10. TXT duplicado, inválido, queda após commit e falha no replace;
11. caminhos customizados sentinela;
12. todas as combinações inválidas de flags;
13. separação Social/Regular no mesmo processo;
14. páginas 504, Cloudflare, formulário, resultados e sessão expirada;
15. smoke opt-in com CAPTCHA humano, sem salvar, verificando a identidade das três categorias e do modal.

## Critérios de aceite da auditoria

| Critério do plano | Situação |
|---|---|
| caminhos de execução classificados | concluído |
| Social/Regular e quatro modos analisados | concluído |
| dados, persistência e retomada validados | concluído |
| bootstrap Chrome/driver validado | concluído |
| hashes antes/depois idênticos | concluído |
| smoke até filtros/IES/conceito | concluído, com falha Selenium reproduzida |
| leitura das três categorias nas duas modalidades | **não concluída**; caminho Selenium falhou antes da pesquisa e o reCAPTCHA não foi resolvido |

Assim, a auditoria está concluída quanto à análise e classificação, mas **o critério operacional de ponta a ponta permanece reprovado**, não presumido como sucesso. A nova validação das categorias deve ocorrer somente após as correções P0/P1 de seleção e observabilidade, em cópias temporárias e com intervenção humana explícita no CAPTCHA.
