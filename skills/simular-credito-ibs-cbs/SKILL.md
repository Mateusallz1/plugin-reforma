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
- PGDAS-D maior que a receita XML gera `RECEITA_SEM_NOTA_FISCAL`. A diferença é
  tributada no Simples da mesma forma que a receita declarada, sem benefício
  fiscal; a alocação comercial como PF é apenas uma premissa para a análise de
  exigência de crédito, sem afirmar que a pessoa física foi identificada.
- XML maior que PGDAS-D mantém `PENDING_REVENUE_DIVERGENCE` e impede recomendação
  estratégica até revisão.
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
  `SIMULATION_ONLY` e não substituem os valores de IBS/CBS documentados.
- Compras continuam demonstradas mesmo quando a base creditável é zero ou está
  pendente. Natureza não aprovada, evidência legal incompleta e documento sem
  suporte não geram crédito estimado.

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
