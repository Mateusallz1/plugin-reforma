# ADR 0005 — Diferença documental comprovada por componente

## Status

Aceita em 2026-09-01.

## Contexto

O total da NF-e (`vNF`) raramente coincide com a soma de `vProd` dos itens: frete, seguro, outras despesas, IPI e ICMS-ST somam, desconto e ICMS desonerado subtraem. O UC-003B media essa diferença, publicava o valor em `unallocated_document_components` e mantinha `document_item_totals_explained=false` até intervenção humana.

Nenhum desses componentes entrava na conta. A consequência era bloquear competências inteiras por uma diferença que os próprios documentos já explicavam: na base de homologação, cinco documentos travavam duas competências, e todos fechavam exatamente com frete e desconto.

## Decisão

A diferença entre o total do documento e a soma dos itens deve ser comprovada componente a componente, nunca presumida e nunca rateada.

- O UC-002 passa a extrair os valores, e não apenas os códigos: `vSeg`, `vFCPST`, `vII`, `vIPI`, `vIPIDevol`, `vICMSST` e `vICMSDeson` juntam-se a `vDesc`, `vFrete` e `vOutro`, preservando também os totais declarados em `ICMSTot`/`ISSQNtot`.
- O UC-003B decompõe a diferença de cada documento contra a composição oficial dos totais, conferindo os itens por `vProd` e `indTot`, e registra o resultado em `difference_composition`.
- O que nenhum componente explica permanece em `residual_difference` e é o único valor publicado como não alocado.
- `document_item_totals_explained=true` exige resíduo zero em todos os documentos; `revenue_population_ready` continua derivando desse gate.
- A fila do analista recebe apenas documentos com resíduo, com a composição já apurada, o valor explicado e o resíduo separados.
- A diferença nunca é distribuída entre os itens. O total dos itens permanece igual ao dos documentos de origem, e essa propriedade é fixada por teste.

## Consequências

- Competências bloqueadas por composição documental passam a conciliar; a diferença deixa de ser um número opaco e passa a apontar sua origem.
- Componente ainda não extraído produz resíduo ou estado de composição indisponível e mantém o bloqueio. A falha é fechada: nenhuma diferença é dada por explicada sem evidência.
- O contrato público do UC-002 vai a `1.2.0` e o do UC-003B a `1.2.0`; artefatos anteriores são rejeitados pelo coordenador e pelo lote.
- Nenhuma conclusão tributária decorre desta decisão: `uc004_planning_authorized` permanece falso.
