Problema
- O `--check` pode gerar falso negativo de curso ("MEDICINA não disponível") por timing/instabilidade de Select2, reduzindo confiança no resultado final.

Abordagem proposta
- Tornar a validação de curso no `--check` mais resiliente com retentativas e verificação dupla antes de concluir indisponibilidade.
- Diferenciar falha transitória de indisponibilidade real em logs e artefatos.
- Preservar comportamento atual do scraper principal, mudando apenas o caminho do `--check` e funções diretamente relacionadas.

Todos
1) Robustez de seleção no `--check`
- Em `aplicar_filtros`/`run_checker`, adicionar retentativas para seleção de município+curso com pequena espera incremental.
- Reexecutar validação `curso_existe("MEDICINA")` antes de marcar município como sem curso.

2) Critério de decisão confiável
- Só classificar "MEDICINA indisponível" após N tentativas consistentes.
- Se houver erro técnico (stale/timeout/select2 fechado), registrar como "falha transitória" e tentar novamente no mesmo município.

3) Telemetria de auditoria do `--check`
- Registrar contadores no fim: municípios verificados, pulados por indisponibilidade confirmada, recuperados após retry, falhas transitórias.
- Opcionalmente gerar arquivo de auditoria do check (separado dos faltantes) para rastreabilidade.

4) Garantias de não regressão
- Manter gravação imediata de faltantes já implementada.
- Manter separação de faltantes por modalidade (social/regular).
- Não alterar regra de coleta de notas (ampla/ppiq/pcd).

Notas
- Meta principal: reduzir falsos negativos sem mascarar indisponibilidades reais.
- Ajustes devem ser locais e reversíveis, priorizando confiança operacional do `--check`.
