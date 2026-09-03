---
name: simular-credito-ibs-cbs
description: Gera uma previsão de crédito e de exposição comercial usando a receita PGDAS-D conciliada e as compras documentais por regime de fornecedor. Use depois das revisões operacionais; não use para declarar crédito legal, alterar regime ou concluir conformidade.
---

# Simular crédito e exposição comercial

Esta skill executa o primeiro UC-004 do planejamento. Ela consolida somente o
período ou a carteira explicitamente indicada, preservando cada competência e
estabelecimento nos artefatos locais.

## Pré-condições

- UC-001 autorizado;
- UC-002 e UC-003 concluídos com as saídas vigentes;
- UC-003D com fornecedores e clientes apurados;
- saídas de aquisições, receitas e conciliação com `simulation_authorized=true`;
- PGDAS-D conciliado. Em carteira com matriz e filiais, a consolidação do grupo
  precisa estar completa para recomendar o modelo híbrido;
- cenário de taxas aprovado pelo analista. O snapshot embarcado é somente uma
  premissa inicial de previsão.

## Caminho rápido

1. Execute `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-credit-planning.ps1 -Folder <pasta>`.
2. Leia `10_PLANEJAMENTO_CREDITOS/credit-planning-summary.json` ou `portfolio-credit-planning-summary.json`.
3. Leia os artefatos locais somente quando o analista solicitar o detalhamento por fornecedor.
4. Use `-MeetingReport` para gerar `10_PLANEJAMENTO_CREDITOS/credit-planning.local.md`.

## Regras

- A receita-base é a receita PGDAS-D conciliada do período. O período não é uma
  média mensal: soma exatamente as competências selecionadas.
- PGDAS-D maior que a receita XML gera uma lacuna de suporte documental. Se o
  estabelecimento não possui documentos no período, classifique-a como
  `ESTABLISHMENT_DOCUMENTS_MISSING`; se possui documentos, mas não para a
  atividade declarada, classifique-a como `DECLARED_WITHOUT_DOCUMENT_SUPPORT`.
  Nenhum desses estados permite inferir cliente PF. A receita só entra em uma
  categoria de pessoa física quando houver evidência explícita no cadastro ou
  nos documentos.
- XML maior que PGDAS-D mantém `PENDING_REVENUE_DIVERGENCE` e impede recomendação
  estratégica até revisão. No consolidado, `xml_above_pgdas` soma essa direção
  da divergência separadamente de `revenue_without_invoice`; nenhum dos lados é
  descartado no rollup.
- Clientes `REGIME_NORMAL` são a população que exige crédito integral. Simples,
  MEI, nanoempreendedor, PF, condomínios, órgãos públicos e governo ficam fora
  dessa população quando a classificação estiver evidenciada.
- Cliente CNPJ `UNKNOWN` ou `REGIME_INDETERMINADO` exige consulta ao `simples-check`;
  sem snapshot carregado, a recomendação fica `PENDING_CUSTOMER_REGIME_LOOKUP`.
  Após tentativa sem resultado, permanece indeterminado e recebe 0% apenas no
  cenário conservador.
- Acima de 20% da receita PGDAS-D, a saída é `RECOMMEND_HYBRID_REVIEW`; o modelo
  híbrido significa IBS/CBS no regime regular e demais tributos no PGDAS-D.
- O cenário inicial usa 9% para fornecedor normal confirmado, 1% para Simples e
  0% para MEI, nanoempreendedor, PF ou regime não confirmado. As taxas são
  `SIMULATION_ONLY` e não substituem os valores de IBS/CBS documentados. O
  JSON deve usar somente status reconhecidos; chave desconhecida, taxa vazia ou
  status de fornecedor sem taxa causa erro explícito, nunca alíquota zero por
  fallback.
- Compras continuam demonstradas mesmo quando a base creditável é zero ou está
  pendente. No resumo de crédito, `documentary_purchase_total` é a soma de
  documentos únicos (`UNIQUE_DOCUMENT_TOTAL`), `purchase_base` é o subtotal de
  itens `PURCHASE_CONTEXT` e `pending_base` é somente a parcela elegível ainda
  pendente (`PURCHASE_CONTEXT_ELIGIBLE_PENDING_ITEM_SUBTOTAL`).
- `non_purchase_entry_total` e `ineligible_purchase_context_base` ficam
  separados para impedir que entradas fora de compras ou itens inelegíveis
  pareçam fazer parte da mesma base. Natureza não aprovada, evidência legal
  incompleta e documento sem suporte não geram crédito estimado.
- O arquivo `acquisition-items.local.jsonl` não contém operações fora de
  compras; por isso não existe uma base monetária por item para
  `NON_PURCHASE_ENTRY`. Esse valor só é publicado pelo total documental
  `non_purchase_entry_total`.
- `simulation_authorized` libera somente esta simulação operacional. O gate
  `uc004_planning_authorized` permanece separado e falso enquanto não houver
  autorização fiscal/legal do planejamento.
- No consolidado por carteira, PGDAS-D, receita documental e divergências só
  entram no rollup quando todos os estabelecimentos da competência estão em
  `reconciliation_mode=ESTABLISHMENT`. Competências em `GROUP` ficam nos
  detalhes e são listadas em `reconciliation_rollup_skipped_periods`.

## Saídas

```text
10_PLANEJAMENTO_CREDITOS/
├── credit-planning-summary.json
├── credit-planning.local.jsonl
└── credit-planning.local.md  # somente com -MeetingReport
```

O JSON público contém somente totais, percentuais, cenários e gates. Nomes,
CNPJs, produtos e detalhes por fornecedor ficam no JSONL local ou no relatório
solicitado. Nenhuma saída autoriza por si só crédito, débito ou mudança de regime.
