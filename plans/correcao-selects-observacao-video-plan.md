# Correção dos selects a partir da gravação

Data: 05/09/2026. Status: mapeamento concluído e plano preparado; implementação pendente.

O objetivo é selecionar cada filtro no campo correto, reconhecer uma seleção já aplicada e esperar o carregamento necessário sem reabrir os mesmos controles. O principal caso de regressão é Manaus: o vídeo mostra `MEDICINA` sendo digitado na busca de IES, seguido de avanço para Parintins sem uma pesquisa de Manaus visível.

## 1. Evidências e limites do diagnóstico

Fonte: [gravação original](<C:/Users/Eduardo/Videos/2026-09-05 13-05-34.mp4>), com 51,371 segundos, 1920 × 1080 e 60 quadros/s. Foram examinados quadros a cada dois segundos em toda a gravação e a cada meio segundo nas transições dos filtros. Os tempos abaixo são aproximados. A análise é visual; não há log de rede sincronizado nem identificação, por evento, de quem produziu cada clique. O código consultado é o estado atual após a reversão da correção anterior.

| Tempo | Observação na gravação | O que permite concluir |
| --- | --- | --- |
| 08–11,5 s | Estado mostra `AMAZONAS - AM`. Tefé aparece brevemente; depois Manacapuru e Medicina são selecionados. O município Manacapuru é reaberto. | Há reabertura de campo já preenchido. A passagem por Tefé precisa ser reproduzida para distinguir efeito da listagem de outra interação. |
| 12–19 s | Medicina está selecionada em Manacapuru; IES permanece desabilitada e depois fica disponível. | Existe espera real pela dependência Curso → IES. Repetir a seleção do curso durante essa espera pode ser desnecessário. |
| 19,5–20 s | A IES de Manacapuru aparece; o terminal informa `IES já presente no CSV, pulando`. | Esse salto é explicado pela regra de progresso, não por indisponibilidade de curso. |
| 21,5–34 s | Curso abre com opções em Manaus, fecha sem Medicina selecionada e permanece em `-- Selecione --`; IES e Conceito ficam desabilitados. | Houve abertura de lista sem aplicação do valor. A tela não prova erro HTTP nem permite atribuir a pausa de cerca de 14 segundos a uma requisição. |
| 35–36,5 s | Curso é aberto novamente; Medicina aparece selecionada em 35,5 s. Depois Município e Curso são reabertos. | Corrige a leitura inicial do mapeamento: Medicina aparece **antes** da reabertura do município aos 36 s. Há repetição mesmo depois de o valor aparecer. |
| 40–40,5 s | A busca de IES mostra `FACULDADE SANTA TERESA (18684)`. Em seguida recebe `MEDICINA` e exibe `Nenhum resultado encontrado`. | O termo de curso chegou ao campo de instituição. A mensagem vazia pertence à busca de IES; não prova ausência de Medicina em Manaus. |
| 41,5–42 s | A execução muda para Parintins, sem uma tela de pesquisa de Manaus nesse intervalo. | Existe risco de omissão de município. A gravação sozinha não prova o conteúdo final dos CSVs. |
| 43–46 s | Parintins recebe Medicina; Município é reaberto; a IES `(26860)` já aparece selecionada enquanto uma nova busca pelo seu nome é digitada. | A seleção visível não encerra todas as interações com aquele filtro. |
| 47–51 s | Conceito 5 é selecionado, a pesquisa de Parintins abre e a tabela é expandida. | O fluxo chega aos resultados em Parintins. |

![Curso selecionado, IES disponível e termo de curso digitado na IES](C:/Projetos/automatizacao_fies_med/plans/evidencias-selects/manaus-curso-no-campo-ies.png)

## 2. Mapeamento no código

### A. Input e resultados sem vínculo com o campo solicitado — prioridade máxima

`select2`, `select2_exact`, `curso_existe` e o fallback de IES encontram o input por `//input[contains(@class,'select2-search__field')]`, sem verificar a qual select ele pertence. Os resultados também são buscados por classes globais. Referências: [select2.py:43](C:/Projetos/automatizacao_fies_med/src/actions/select2.py:43), [select2.py:75](C:/Projetos/automatizacao_fies_med/src/actions/select2.py:75), [select2.py:144](C:/Projetos/automatizacao_fies_med/src/actions/select2.py:144), [select2.py:330](C:/Projetos/automatizacao_fies_med/src/actions/select2.py:330).

Se o dropdown esperado fechar e outro abrir durante a espera, o input encontrado pode ser o da IES. O código oferece um mecanismo concreto compatível com o quadro de 40,5 s. A reprodução deve confirmar qual operação estava aguardando, pois o vídeo não contém rastreamento das chamadas.

Restringir apenas a `.select2-container--open` ainda é insuficiente: o dropdown aberto pode pertencer ao controle errado.

### B. Duas camadas reaplicam os mesmos filtros

O fluxo principal chama `aplicar_filtros(estado, municipio, curso)` em [runner.py:1034](C:/Projetos/automatizacao_fies_med/src/scraping/runner.py:1034). Depois chama `buscar_notas_por_municipio`, que seleciona o município e verifica/seleciona o curso novamente em [runner.py:524](C:/Projetos/automatizacao_fies_med/src/scraping/runner.py:524).

Além disso, `curso_existe` abre a lista e fecha sem selecionar; `select2_exact` abre a lista novamente. Essa sequência ocorre em [flow.py:145](C:/Projetos/automatizacao_fies_med/src/navigation/flow.py:145). As reaberturas, portanto, podem acontecer mesmo sem erro ou timeout.

### C. Fechamento por clique no corpo da página

As ações encerram listas com `body.click()`, inclusive depois de apenas listar opções. Esse comando não representa semanticamente “fechar dropdown”. O Selenium clica no centro do elemento, o que depende da geometria visível e pode coincidir com um controle descendente. Essa hipótese deve ser testada contra a passagem por Tefé e a seleção de IES após listagem, sem atribuir esses eventos ao clique antes da reprodução. [Documentação do Selenium sobre cliques](https://www.selenium.dev/documentation/webdriver/elements/interactions/).

### D. Busca e identidade da IES estão misturadas

O chamador remove o código em [runner.py:571](C:/Projetos/automatizacao_fies_med/src/scraping/runner.py:571), enquanto `select2_exact` compara o nome digitado com o texto integral da opção. Quando o rótulo contém `(26860)`, a igualdade com apenas o nome falha e pode provocar uma segunda abertura pelo fallback.

O fallback pode escolher o primeiro item sem correspondência e valida `candidato.text` depois do clique em [select2.py:373](C:/Projetos/automatizacao_fies_med/src/actions/select2.py:373). Esse elemento pode já ter sido removido do DOM. A validação deve usar a identidade solicitada, capturada antes da interação, e o estado atual do formulário.

### E. Confirmação precisa ser específica por tipo de campo

O mapa de estados envia `Amazonas` em [estados.py:7](C:/Projetos/automatizacao_fies_med/src/config/estados.py:7); a tela exibe `AMAZONAS - AM`. A igualdade estrita utilizada na correção revertida rejeitaria esse valor correto. Reaplicar aquela regra genericamente reproduziria as tentativas desnecessárias relatadas.

Por outro lado, comparação por substring para curso aceitaria `BIOMEDICINA` ou `MEDICINA VETERINÁRIA`. Precisamos de regras distintas para UF, município, curso, IES e conceito.

### F. Esperas e falhas se confundem com indisponibilidade

No modo rápido, `select2()` pressiona Enter após uma pausa efetiva de 10–20 ms, sem confirmar o resultado. A listagem considera a contagem estável um sinal de término, embora a resposta ou a página seguinte possa chegar depois. `curso_existe` procura qualquer opção e usa substring.

As operações de filtro são protegidas por `_executar_com_pausa`, mas não recebem uma pós-condição para reconhecer resposta tardia. O controlador pode repetir a ação mesmo quando o formulário já mudou. A espera sem clique deve ser distinguida de uma nova tentativa. A pausa de Manaus no vídeo não comprova um ciclo desse controlador, pois a mensagem de timeout correspondente não está visível.

## 3. Implementação em etapas

### Etapa 1 — Reproduzir a troca de campo e instrumentar o diagnóstico

Antes de mudar o fluxo, criar um teste com Select2 real que abra Curso, feche esse dropdown durante a espera e abra IES. A chamada pendente de Curso deve falhar no código antigo ou expor a escrita no campo errado. Registrar também a listagem sobre uma opção posicionada no centro visível do `body`.

Adicionar diagnóstico restrito aos filtros: operação, campo esperado, dono do dropdown encontrado, termo de busca, valor selecionado, etapa, duração, motivo de recuperação e contagem de abertura/digitação/clique. Não registrar cookies, tokens, payloads ou conteúdo das tabelas de candidatos. Esperas normais podem ficar no nível de diagnóstico; o terminal deve destacar recuperação efetiva, mudança de etapa e falha.

### Etapa 2 — Garantir que cada interação pertença ao select certo

Centralizar a resolução de select original, container renderizado, dropdown, input e lista de resultados.

- Inspecionar o DOM real para estabelecer a associação por IDs e atributos ARIA. Usar `aria-controls`/`aria-owns` quando disponíveis; não presumir que a convenção de nomes cobre todas as versões.
- Confirmar essa associação antes de limpar, antes de digitar e antes de clicar em opção. Se outro dropdown aparecer, invalidar a operação pendente; nunca aproveitar o input encontrado apenas porque está visível.
- Relocalizar elementos após recriação do DOM e revalidar o dono. A ausência de prova de associação deve impedir a digitação, em vez de liberar um fallback global.
- Consultar o estado desabilitado do select original e de seus ancestrais. Não remover bloqueios ou forçar habilitação para declarar o campo pronto.
- Fechar o dropdown pertencente à operação com Escape no seu input/seleção e verificar que fechou. Se a versão exigir outro mecanismo, usar o método `close` do Select2 associado ao ID, sem alterar seu valor. [Métodos oficiais do Select2](https://select2.org/programmatic-control/methods/).
- Garantir que listar opções e fechar a lista preserve a seleção e não dispare `change` indevido.

### Etapa 3 — Separar termo de busca, identidade e seleção confirmada

| Campo | Busca | Confirmação |
| --- | --- | --- |
| Estado | Nome ou UF, conforme o portal | Valor original associado à UF; admitir a decoração comprovada `NOME - UF`. `Amazonas` deve corresponder a `AMAZONAS - AM`, sem aceitar outro estado. |
| Município | Nome | Nome normalizado completo, sob a UF atual. |
| Curso | `MEDICINA` | Nome normalizado completo ou identificador conhecido; rejeitar Biomedicina e Medicina Veterinária. |
| IES | Nome sem código quando exigido pela pesquisa | Código esperado, inclusive códigos de 1–3 dígitos; sem código, nome completo único. Nunca escolher outra instituição como fallback. |
| Conceito | Valor desejado ou primeira opção válida quando autorizado pelo fluxo | Valor aplicado no próprio campo; excluir placeholders, mensagens e opções desabilitadas. |

Ler o select original quando presente e conferir sua correspondência com a seleção exibida. Não impor igualdade literal a representações formatadas. Capturar o rótulo/código esperado antes do clique e confirmar em elementos relocalizados, sem consultar uma opção removida.

Se o campo já estiver correto dentro da dependência atual, retornar sucesso sem abrir, digitar ou disparar `change`. A validação deve considerar UF → município → curso → IES, para não reutilizar um valor antigo que permaneceu no DOM durante uma troca de pai.

### Etapa 4 — Remover reaplicações duplicadas

Concentrar a preparação dos filtros em `aplicar_filtros`. Integrar verificação de existência e seleção do curso em uma única operação: uma lista carregada permite selecionar Medicina ou confirmar sua ausência, sem fechar e abrir novamente.

Em `buscar_notas_por_municipio`, remover o bloco duplicado de seleção e utilizar a mesma operação de garantia dos filtros, que será idempotente. Revisar todos os chamadores antes da remoção para preservar chamadas diretas. Uma segunda chamada pode validar o estado; não deve gerar novos cliques quando ele já estiver correto.

Reusar o mesmo contrato no fluxo normal, `--check`, `--review`, `--faltantes-txt`, “Nova Consulta” e restauração do checkpoint. Mudar município deve invalidar apenas os filtros dependentes; reaplicar a mesma UF não deve limpá-los.

### Etapa 5 — Esperar conclusão e recuperar apenas o necessário

Tratar explicitamente os estados: selecionado; carregando; ausente confirmado; falha de interação; falha de servidor.

- Esperar opção selecionável e resultados vinculados ao campo. “Carregando”, lista temporariamente vazia e erro de consulta não são ausência confirmada.
- Paginação deve esperar a próxima resposta/mudança de conteúdo, sem encerrar só porque a quantidade de opções ainda não mudou. [AJAX e paginação do Select2](https://select2.org/data-sources/ajax/).
- Usar um prazo por operação lógica, aproveitando os limites existentes; não multiplicar o timeout completo por cada etapa e cada camada de retry. Uma resposta concluída deve liberar o fluxo imediatamente, sem uma pausa longa fixa adicional.
- Acompanhar requisições da operação e das dependências relevantes. Não condicionar todo o formulário a qualquer AJAX global. Distinguir recebimento de headers da conclusão do corpo; não mudar silenciosamente a semântica compartilhada de `NetworkTracker.terminal` sem testar os consumidores de tabela/pesquisa.
- Quando a rede não estiver disponível, usar pós-condições do DOM, com o mesmo vínculo de campo. Registrar a limitação do diagnóstico, não presumir sucesso de rede.
- Antes de repetir, verificar se a seleção anterior chegou atrasada. Para operações com retorno booleano, não usar diretamente `concluida` de `com_retry_timeout`, que hoje retorna `None` quando detecta conclusão tardia; devolver um resultado tipado correto ou tratar a conclusão dentro da operação idempotente.
- Para falha de interação, permitir até duas recuperações locais além da tentativa inicial, somente quando houver condição concreta: dropdown errado/fechado, elemento recriado ou clique não aplicado. Elemento recriado com seleção já correta não exige novo clique.
- Uma requisição ainda em andamento dentro do prazo não gera tentativa adicional. Falha HTTP/timeout de servidor continua no mecanismo existente de recuperação pelo checkpoint.
- Depois de esgotar a recuperação local, reconstruir uma vez os filtros do município atual. Se a interação continuar inválida, encerrar essa execução com diagnóstico e progresso preservado, sem declarar o município indisponível nem avançar silenciosamente. Falhas transitórias não geram remoção de faltantes nem registros de ausência.

## 4. Testes e critérios de aceitação

Os testes precisam exercitar comportamento do navegador e efeitos de `change`, além das unidades de normalização. Priorizar os casos que reproduzem a gravação.

| Caso | Resultado exigido |
| --- | --- |
| Curso fecha e IES abre enquanto a busca está pendente | Zero caracteres de `MEDICINA` no input de IES; recuperação restrita ao Curso. |
| Listagem com opção no centro do corpo da página | A seleção original é preservada; nenhum clique acidental em opção ao fechar. |
| Estado `AMAZONAS - AM`, alvo `Amazonas` | Confirmação válida na primeira tentativa. |
| Município/curso já selecionados; mesma chamada repetida | Zero novos cliques, digitações e eventos `change` nesses campos. |
| Troca real de município com resposta atrasada do anterior | Somente opções do município atual são usadas. |
| Curso retorna após 0,2 s, 2 s, 8 s ou perto do prazo | Uma consulta por tentativa; espera sem reabrir e sem salto indevido. |
| Clique não aplica seleção | Recuperação local limitada, com motivo registrado. |
| DOM é recriado depois de a seleção ter sido aplicada | Relocalização e confirmação sem repetir o clique. |
| IES com nome e código, nomes duplicados ou código curto | Código correto preservado; ambiguidade ou divergência nunca aceita como sucesso. |
| Resultado vazio em IES durante uma operação de Curso | Não classifica Medicina como ausente. |
| Ausência real de Medicina | Reconhecida apenas após conclusão da lista correta; o motivo é explícito. |
| Paginação lenta com contagem temporariamente igual | Todas as páginas são lidas. |
| HTTP 504 ou resposta tardia | Checkpoint e operação preservados; resposta tardia não produz clique duplicado. |
| CAPTCHA pendente/expirado ou janela encerrada | Mantém o tratamento existente e a intervenção humana prevista. |

Executar a suíte existente (`python -B -m unittest discover -s tests -v`) e os testes novos. Os cenários de navegador devem usar Select2 real, incluir o rótulo `AMAZONAS - AM`, controles sobrepostos, troca do dropdown ativo e recriação de dependências. Um fixture com um único campo ou apenas nomes idênticos não cobre o problema observado.

Critérios para considerar a correção pronta:

1. Nenhuma operação escreve ou lê resultados de outro filtro.
2. Reaplicação do mesmo contexto produz apenas verificações, sem novos `change`.
3. Nenhum município é abandonado por falha de interação ou por lista ainda carregando.
4. Cada retry tem causa registrada; não aparece retry para seleção válida com rótulo decorado.
5. Os cenários locais passam e a validação visual no portal confirma o comportamento real.

## 5. Validação visual no portal

A validação final deve ocorrer no Chrome visível, com acompanhamento da tela conforme solicitado pelo usuário. O usuário atua nas verificações humanas; a automação conduz os filtros. Observar diretamente antes e depois de cada ação relevante, sem depender apenas dos resultados dos testes locais.

Executar uma rodada limitada a Amazonas → Manacapuru → Manaus → Parintins. Registrar tempos, campo alvo, campo efetivamente aberto, valor final, número de aberturas e motivo das recuperações. Reproduzir o caso de Manaus até chegar à instituição e à pesquisa correta, sem saltar para Parintins por um resultado vazio em outro campo. Em Manacapuru, distinguir o salto previsto por IES já gravada de falha de seleção.

Usar cópias dos arquivos de progresso e caminhos de saída de teste para a rodada diagnóstica, preservando os CSV/TXT oficiais. Após evidenciar a correção, a execução normal utiliza os arquivos oficiais existentes. Não apagar dados nem remover entradas de faltantes apenas para facilitar o teste.

O controle visual do computador foi bloqueado nas duas tentativas anteriores por falha da ferramenta ao identificar a URL do Chrome. Uma nova tentativa deve verificar se essa condição foi resolvida. Se o bloqueio persistir, registrar que a validação visual ao vivo está pendente; não substituir sua comprovação por um teste headless. A gravação fornecida permite concluir o mapeamento e preparar este plano.

## 6. Arquivos e sequência de entrega

| Arquivo | Trabalho previsto |
| --- | --- |
| `src/actions/select2.py` | Associação dos elementos ao campo; abertura/fechamento seguros; confirmação por identidade; seleção idempotente; recuperação local. |
| `src/navigation/flow.py` | Preparação única dos filtros e seleção do curso sem dupla abertura. |
| `src/scraping/runner.py` | Remover reaplicações com efeitos duplicados; preservar código de IES; impedir salto após falha técnica. |
| `src/core/network.py`, `src/core/retry.py` | Ajustar apenas contratos necessários à correlação/retorno, com testes dos consumidores existentes. |
| `tests/` | Regressões do vídeo e cenários reais de Select2 no navegador. |
| `README.md` | Documentar o comportamento confirmado e os comandos de validação após a implementação. |

Entregar primeiro a reprodução e a correção do campo errado/fechamento. Depois a confirmação por identidade e a remoção das duplicações. Por último, ajustar esperas e recuperação com base nos testes e nas medições. Aumentar timeouts ou aplicar três tentativas a todos os helpers não substitui essas correções.

Checklist do plano:

- [x] Examinar a gravação e marcar os eventos relevantes.
- [x] Cruzar eventos com o código, separando observação e hipótese.
- [x] Registrar a falha da comparação de UF na correção revertida.
- [x] Definir implementação, regressões e validação visual.
- [ ] Implementar as etapas propostas.
- [ ] Executar os testes e a rodada visual limitada no portal.
- [ ] Documentar o resultado observado e liberar a execução normal.
