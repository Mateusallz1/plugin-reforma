# UC-003B - Revisão das receitas

## Objetivo

Apresentar receitas documentais, devoluções, remessas e operações pendentes sem confundir CFOP do fornecedor com receita da empresa analisada e sem substituir o valor total da nota pela soma dos itens.

## Classificações

- `REVENUE_GOODS`: NF-e/NFC-e de saída com CFOP usual de venda homologado;
- `REVENUE_SERVICES`: NFS-e prestada;
- `REVENUE_TRANSPORT`: CT-e prestado;
- `SALES_RETURN_INBOUND`: devolução de venda recebida em entrada e reconhecida pelo checklist;
- `PURCHASE_RETURN_OUTBOUND`: devolução de compra emitida em saída;
- `NON_REVENUE_REMITTANCE`: CFOP com `indRemes=1`;
- `NON_REVENUE_RETURN`: retorno oficial sem natureza de devolução;
- `NON_REVENUE_ANNULMENT`: anulação oficial;
- `MIXED_DOCUMENT_PENDING_ALLOCATION`: nota com itens em classes distintas;
- `PENDING_REVENUE_TREATMENT`: saída não contemplada no checklist nem nos indicadores oficiais.

## Valores

O total da NF-e/NFC-e vem do `gross_amount` do UC-001, correspondente ao `vNF`. O UC-002 fornece `vProd` por item. A diferença permanece em `unallocated_document_components` e exige explicação; não é descartada nem rateada automaticamente.

`net_documentary_revenue_candidate` corresponde à receita operacional documental menos devoluções de venda recebidas. É indicador preparatório, não base tributável concluída.

## Saídas

```text
06_REVISAO_RECEITAS/
├── revenue-summary.json
├── revenue-documents.local.jsonl
├── fila-revisao-receitas.csv
├── cfop-ruleset-lock.json
└── relatorio-revisao-receitas.md
```

## Decisão do analista

O arquivo opcional `00_CONTROLE/classificacao-receitas.csv` exige:

```text
document_ref;classificacao;status;aprovado_por;observacao
```

Somente linhas `APROVADO` substituem classificação automática. Referência desconhecida, decisão conflitante ou classificação não permitida gera falha operacional.

## Gates

- `uc003_revenue_execution_ready`;
- `revenue_review_required`;
- `cfop_classification_complete`;
- `document_item_totals_explained`;
- `revenue_population_ready`: a apuração de receita foi concluída sem pendência de CFOP nem diferença inexplicada. Uma competência sem documento de saída apura zero e satisfaz o gate; zero é valor apurado, não população ausente;
- `analyst_review_required`;
- `uc004_planning_authorized`, sempre falso nesta fase.
