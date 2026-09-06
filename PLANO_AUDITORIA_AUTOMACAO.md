# Plano de auditoria completa da automação FIES

## Resumo

- Auditar o projeto atual sem corrigir código nem alterar CSVs/TXTs oficiais.
- Considerar o Windows como runtime oficial: Python 3.14.5, Selenium 4.48.0, webdriver-manager 4.1.2, Pandas 3.0.5 e Chrome.
- Cobrir modalidades Social e Regular e os modos normal, `--check`, `--review` e `--faltantes-txt`.
- Criar `AUDITORIA_AUTOMACAO.md` com evidências reproduzíveis, severidade, impacto e correção mínima recomendada.
- Classificar tanto interrupções explícitas quanto travamentos, falsos sucessos, dados incorretos e itens silenciosamente ignorados.

## Execução da auditoria

- Mapear o fluxo completo: inicialização → Cloudflare/CAPTCHA → modalidade → Estado/Município/Curso/IES → conceito → pesquisa → categorias → modal → persistência → retomada.
- Revisar seletores, esperas, verificação pós-clique, stale elements, paginação, troca de categoria, fechamento de modal, 504, retries, sessão expirada e bloqueios por `input()`.
- Examinar todos os `except`, `pass`, retornos vazios e `continue` para identificar onde erros reais são ocultados e a execução termina como concluída.
- Auditar persistência e recuperação: escrita interrompida, arquivo aberto no Excel, corrupção parcial, concorrência entre instâncias, retomada por última linha, município parcialmente processado, deduplicação e separação por modalidade.
- Auditar contratos dos modos CLI, precedência de flags, caminhos customizados, arquivo de falhas, remoção de faltantes e divergências entre README e comportamento.
- Verificar bootstrap do ChromeDriver, dependência de rede/cache, compatibilidade das versões instaladas e comportamento quando navegador, driver ou portal ficam indisponíveis.
- Validar os dados existentes: esquema, linhas truncadas, campos obrigatórios, duplicatas, notas fora de faixa, códigos de IES, ordem de retomada e coerência entre CSVs, faltantes e falhas.
- Registrar como evidências iniciais já confirmadas:
  - duas linhas truncadas no CSV Regular;
  - detecção de conceitos vazios retornando zero alvos por causa de valores `NaN`;
  - ordem dos CSVs incompatível com a retomada baseada exclusivamente na última linha;
  - exceções amplas capazes de encerrar etapas silenciosamente;
  - desafio Cloudflare ativo antes da página de consulta.

## Validação controlada

- Registrar hashes SHA-256 dos CSVs/TXTs oficiais antes e depois para provar que o teste não os alterou.
- Executar no Windows um smoke test temporário, sem salvar resultados nem falhas, usando inicialmente `AC / CRUZEIRO DO SUL / IES 24547`.
- Percorrer Social e Regular até a leitura das três categorias, validando em cada transição o valor realmente selecionado e a origem da tabela/modal.
- Se o alvo não estiver mais disponível, registrar a divergência e usar a primeira IES atualmente oferecida no Acre somente para concluir a validação mecânica.
- Simular em arquivos temporários: CSV truncado, município parcialmente salvo, linhas fora de ordem, campos vazios, TXT duplicado/inválido, arquivo bloqueado e exceções nos pontos críticos.
- Não executar uma coleta nacional completa; ela acrescentaria duração e risco aos dados sem ampliar materialmente a cobertura estrutural da auditoria.

## Relatório e critérios de aceite

- Organizar achados como P0–P3, contendo: evidência, caminho afetado, cenário de reprodução, tipo de falha, impacto, alcance, correção mínima e teste de regressão recomendado.
- Separar problemas confirmados de riscos dependentes do comportamento momentâneo do portal.
- Incluir matriz dos quatro modos × duas modalidades e um plano de correção ordenado por risco operacional.
- Não adicionar dependências, frameworks ou testes permanentes; os diagnósticos auxiliares serão temporários.
- Nenhuma API pública será alterada. O único arquivo novo versionável será `AUDITORIA_AUTOMACAO.md`.
- A auditoria estará concluída quando todos os caminhos de execução estiverem classificados, o smoke test estiver documentado e os hashes confirmarem que os artefatos oficiais permaneceram intactos.

## Premissas

- O usuário estará disponível para resolver Cloudflare/CAPTCHA durante o smoke test.
- Ausência das dependências no WSL será registrada apenas como diferença ambiental, pois o alvo oficial escolhido é Windows.
- O estado atual do disco é a versão auditada; alterações aparentes causadas somente por finais de linha não serão tratadas como mudanças funcionais.
