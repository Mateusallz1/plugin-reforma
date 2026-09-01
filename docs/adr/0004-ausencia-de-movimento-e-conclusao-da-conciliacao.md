# ADR 0004 — Ausência de movimento é conclusão da conciliação

## Status

Aceita em 2026-09-01.

## Contexto

O UC-001 marcava grupos sem documento como `SEM_MOVIMENTACAO`, e o UC-003B publicava `REVENUE_REVIEW_NO_MOVEMENT` quando não encontrava documento de saída. Ambos decidiam pela contagem de arquivos e afirmavam um fato do negócio a partir de uma evidência que só cobre documentação.

O efeito prático era circular: `revenue_population_ready` exigia pelo menos um registro, o UC-003C recusava executar sem esse gate, e a competência sem nota nunca chegava à declaração — justamente a fonte que provaria se houve operação. Na base de homologação, uma competência com R$ 15.778,00 declarados no PGDAS-D era classificada como sem movimentação e não era conciliada.

## Decisão

Ausência de documento é fato documental. Ausência de movimento é conclusão e exige as duas fontes.

- `SEM_MOVIMENTACAO`, `COM_MOVIMENTACAO` e `MOVIMENTACAO_RESTRITA` passam a `SEM_DOCUMENTO`, `COM_DOCUMENTO` e `DOCUMENTO_RESTRITO`; o campo `movement_status` passa a `document_status`.
- `REVENUE_REVIEW_NO_MOVEMENT` e `ACQUISITION_REVIEW_NO_MOVEMENT` passam a `REVENUE_REVIEW_NO_DOCUMENT` e `ACQUISITION_REVIEW_NO_DOCUMENT`.
- `revenue_population_ready` passa a significar apuração concluída e confiável, sem exigir registros. Receita documental zero é valor apurado e satisfaz o gate; pendência de CFOP ou diferença inexplicada continuam bloqueando.
- O UC-003C ganha o estado `NO_MOVEMENT`, atribuído somente quando documentação e declaração são zero na atividade. Ele conta como conciliado e não gera aviso.
- Declaração positiva sem documentação continua `DECLARED_WITHOUT_DOCUMENT_SUPPORT` e continua exigindo revisão do analista.

## Consequências

- Competência sem nota fiscal é conciliada em vez de ignorada; na homologação, as conciliações produzidas passaram de 10 para 12 em 14 competências, revelando R$ 23.019,20 declarados sem suporte documental que antes não eram reportados.
- As duas competências que permanecem bloqueadas o são por `document_item_totals_explained=false`, um defeito independente.
- `non_issuance_confirmed` e `uc004_planning_authorized` continuam falsos; nenhum estado desta decisão comprova não emissão.
- O contrato público do UC-001 vai a `1.9.0`, o do UC-003B a `1.1.0`, o do UC-003C a `1.1.0` e o do status a `1.1.0`.
- `BATCH_SCHEMA_VERSION` vai a `1.2.0` para invalidar competências processadas com o vocabulário anterior.
- Artefatos gerados antes desta versão usam os nomes antigos e precisam ser reprocessados.
