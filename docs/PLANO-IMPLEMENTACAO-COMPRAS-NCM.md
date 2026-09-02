# Plano de implementação — compras documentais e triagem NCM × descrição

## Estado

Implementado e validado em 2026-09-02. Este documento permanece como contrato
operacional e registro das decisões que limitam o incremento; não autoriza
inferir crédito, benefício, margem, estoque, omissão ou reclassificação.

Antes de alterar código, leia `AGENTS.md`, `docs/PLANO-DE-CONCLUSAO.md` e este
arquivo; confirme `git status` e `git log -1` e preserve mudanças externas.

## Objetivos

1. Apurar todas as compras documentais válidas por estabelecimento e
   competência, sem excluir compras por ausência ou vedação futura de crédito.
2. Comparar compras e vendas documentais como instrumento de auditoria, sem
   concluir margem, estoque, omissão, receita tributável ou infração.
3. Criar triagem rastreável entre descrição e NCM, sem reclassificação automática
   e sem presumir benefício de IBS/CBS.
4. Manter os detalhes comerciais somente em artefatos locais e restritos.

## Decisões fechadas

### Terminologia

- Use **compras documentais válidas**, não “compras efetivamente realizadas”.
  XML válido comprova documento fornecido, não pagamento, entrega, recebimento,
  propriedade ou realização econômica.
- Use **total bruto documental de compras** para a soma dos documentos únicos de
  entrada/tomados.
- Use **candidato líquido documental de compras** para o total bruto menos
  devoluções de compra emitidas. O nome não representa conclusão contábil.
- Use **triagem NCM × descrição** para a comparação semântica. Não use
  “reclassificação” antes de decisão humana aprovada.

### Total de compras

- A autoridade quantitativa é o documento único do UC-001, identificado por
  `document_ref`, e não a soma dos itens do UC-002.
- Parta somente de documentos `included=true`, `authorized_for_planning=true` e
  de direção `ENTRADA`, mas não trate toda entrada como compra.
- Antes do total, classifique os itens de NF-e/NFC-e por CFOP com a mesma fonte
  oficial usada no UC-003B. Separe `PURCHASE_CONTEXT`, `SALES_RETURN_INBOUND`,
  `NON_PURCHASE_ENTRY` e `PENDING_PURCHASE_TREATMENT`.
- Entradas de devolução de venda, retorno, remessa, transferência ou outra
  operação sem compra não entram em `gross_documentary_purchases`; permanecem
  demonstradas em subtotal próprio.
- Documento com classes mistas não recebe alocação automática: seu total vai para
  `pending_purchase_treatment` e torna a comparação `PARTIAL`.
- NF-e/NFC-e usam o total do documento (`vNF`); NFS-e tomada usa o valor do
  serviço; CT-e tomado usa o valor da prestação.
- Deduplicate por `document_ref`. Representações XML repetidas não podem aumentar
  o total.
- Compras sem crédito, com crédito pendente ou futuramente vedado permanecem no
  total documental. Crédito é uma dimensão posterior e independente.
- Preserve subtotais por modelo e grupo operacional. O consolidado deve informar
  `cross_document_linkage=NOT_PERFORMED` enquanto CT-e e NF-e não forem
  relacionados economicamente; ele não deve ser chamado de custo econômico.
- Devoluções de compra emitidas ficam demonstradas separadamente e reduzem apenas
  o candidato líquido documental.

### Comparação compras × vendas

- Compare somente o mesmo estabelecimento e a mesma competência.
- A comparação depende de UC-003A e UC-003B coerentes e atuais.
- Publique valores brutos, devoluções, candidatos líquidos e razão
  compras/receita quando o denominador for maior que zero.
- `purchase_to_revenue_ratio` significa
  `net_documentary_purchases_candidate / net_documentary_revenue_candidate`,
  serializado como string decimal com quatro casas. Receita líquida candidata
  menor ou igual a zero produz razão `null`, nunca infinito ou divisão por zero.
- Pendência de tratamento em compras ou receitas produz comparação `PARTIAL`.
- Não crie faixas de risco, alertas de margem ou limites automáticos nesta fase.
- O comparativo é informativo e não altera gates de conciliação, crédito ou
  UC-004.

### NCM × descrição

- A descrição do XML é o principal sinal inicial de triagem, mas não é autoridade
  suficiente para classificar a mercadoria.
- Classificação exige, conforme o caso, características técnicas, composição,
  função, uso, materiais, regras da NCM, Notas Legais, Nesh e decisões oficiais.
- Descrição genérica, abreviada, marca, modelo ou texto comercial não pode confirmar
  incompatibilidade.
- Sem catálogo ou ruleset semântico aprovado, a comparação permanece
  `INCONCLUSIVE`. Regra semântica aprovada pode gerar somente a observação local
  `NCM_DESCRIPTION_REVIEW_REQUIRED`.
- Quando a descrição sugerir incompatibilidade, registre
  `suspected_field=NCM` como hipótese inicial; não altere o NCM informado.
- Somente catálogo Produto × NCM `APROVADO` ou decisão humana com evidência técnica
  pode confirmar `PRODUCT_NCM_MISMATCH`.
- A confirmação deve permanecer por item. Outros produtos, serviços e transportes
  elegíveis continuam o fluxo.
- Reclassificação formal e substituição do código ficam para etapa posterior.
- NCM, descrição ou similaridade nunca presumem redução, alíquota zero, crédito ou
  qualquer benefício de IBS/CBS. Benefícios exigem código confirmado, vigência,
  anexo legal e demais condições aplicáveis.

## Fontes oficiais obrigatórias

O agente implementador deve verificar novamente as versões vigentes antes de
criar snapshots ou regras:

- Receita Federal — NCM:
  `https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/ncm`
- Receita Federal — consulta de classificação e caracterização da mercadoria:
  `https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/consultas`
- Receita Federal — Sistema Classif, Notas Legais e Nesh:
  `https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/classif`
- LC 214, texto compilado vigente:
  `https://www.planalto.gov.br/ccivil_03/leis/lcp/lcp214compilado.htm`

Não consultar fontes remotas durante a análise de cliente. O runtime deve usar
snapshot versionado, com fonte, data de verificação e hash; atualização é tarefa
explícita de manutenção.

## Contrato entregue — UC-003A

`ACQUISITION_SCHEMA_VERSION` foi entregue inicialmente em `1.2.0` e está em
`1.5.0` na baseline atual.

Manter `category_amounts` com a semântica atual de subtotal bruto dos itens para
não misturar mudança de nome e de cálculo. Adicionar ao `acquisition-summary.json`:

```json
{
  "documentary_totals": {
    "amount_basis": "UNIQUE_DOCUMENT_TOTAL",
    "document_count": 0,
    "gross_documentary_purchases": "0.00",
    "pending_document_count": 0,
    "pending_purchase_treatment": "0.00",
    "non_purchase_entry_operations": "0.00",
    "by_document_type": {},
    "by_analysis_group": {},
    "cross_document_linkage": "NOT_PERFORMED"
  },
  "excluded_operation_summary": {
    "amount_basis": "UNIQUE_DOCUMENT_TOTAL",
    "document_count": 0,
    "item_count": 0,
    "document_total": "0.00",
    "by_reason": {},
    "mixed_reason_documents": {
      "document_count": 0,
      "document_total": "0.00"
    },
    "reason_document_counts_may_overlap": true
  }
}
```

Requisitos:

- carregar e validar `03_SAIDAS/validation-result.json` na versão vigente;
- validar o encadeamento `validation_id → content_analysis_id → review_id`;
- formar mapa de documentos autorizados por `document_ref`;
- usar um classificador CFOP compartilhado com o UC-003B para impedir que
  devoluções de venda ou remessas de entrada sejam tratadas como compra;
- somar cada documento de entrada uma única vez;
- incluir `validation_id` e os documentos materiais no cálculo de `review_id`;
- o relatório deve separar “total dos documentos” de “subtotal dos itens por
  categoria”.
- documento misto ou pendente permanece fora do total confirmado e aparece em
  `pending_purchase_treatment`.

`document_count` conta somente documentos confirmados como compra;
`pending_document_count` conta documentos aguardando tratamento.

Extrair a classificação CFOP comum para
`engine/src/fiscal_document_intake/operation_classification.py`, consumida por
aquisições e receitas. O launcher de aquisições deve receber e travar o snapshot
CFOP e o ruleset do analista, além do snapshot CST/cClassTrib já existente.

Não criar `credit_eligible_amount` nesta entrega do UC-003. A simulação separada
do UC-004 usa `creditable_base` e `estimated_credit` somente com a marca
`SIMULATION_ONLY`.

## Contrato entregue — devoluções e comparação

`REVENUE_SCHEMA_VERSION` foi entregue inicialmente em `1.3.0` e está em `1.4.0`
na baseline atual, com o campo adicional em `totals`:

```json
{
  "purchase_returns_outbound": "0.00"
}
```

`PLANNING_STATUS_SCHEMA_VERSION` foi entregue inicialmente em `1.3.0` e está em
`1.5.0` na baseline atual. Quando aquisições e receitas
estiverem disponíveis e coerentes, adicionar ao `documentary_summary`:

```json
{
  "purchase_sales_comparison": {
    "status": "AVAILABLE",
    "gross_documentary_purchases": "0.00",
    "purchase_returns_outbound": "0.00",
    "net_documentary_purchases_candidate": "0.00",
    "pending_purchase_treatment": "0.00",
    "gross_operational_revenue": "0.00",
    "sales_returns_inbound": "0.00",
    "net_documentary_revenue_candidate": "0.00",
    "purchase_to_revenue_ratio": null,
    "cross_document_linkage": "NOT_PERFORMED",
    "interpretation": "AUDIT_ONLY"
  }
}
```

Estados permitidos:

- `AVAILABLE`: ambas as populações estão apuradas;
- `PARTIAL`: uma frente está ausente ou alguma população possui tratamento
  pendente;
- `NOT_APURADO`: nenhuma frente foi concluída.

`AVAILABLE` exige compras sem tratamento pendente e receita pronta. Havendo
documento misto ou valor pendente em qualquer frente, use `PARTIAL` e mantenha os
valores já apurados visíveis.

O relatório do coordenador deve mostrar a seção **Compras documentais × vendas
documentais** depois do resumo de aquisições e receitas. Não mostrar códigos de
gate na conversa comum.

## Contrato entregue — triagem NCM × descrição

`CONTENT_SCHEMA_VERSION` foi entregue inicialmente em `1.3.0` e está em `1.4.0`
na baseline atual, com os novos campos por produto:

```json
{
  "ncm_description_review": {
    "status": "INCONCLUSIVE",
    "basis": "XML_DESCRIPTION_ONLY",
    "suspected_field": null,
    "reported_ncm": "00000000",
    "approved_ncm": null,
    "evidence_ref": null,
    "reason_codes": []
  }
}
```

Estados permitidos:

- `NOT_APPLICABLE`: registro não é produto;
- `UNVERIFIABLE`: descrição ou NCM ausente/malformado;
- `INCONCLUSIVE`: não há referência aprovada suficiente;
- `REVIEW_REQUIRED`: indício semântico não bloqueante;
- `ANALYST_CONFIRMED_MATCH`: decisão aprovada confirma o código;
- `ANALYST_CONFIRMED_MISMATCH`: decisão aprovada confirma divergência.

Bases permitidas:

- `XML_DESCRIPTION_ONLY`;
- `OFFICIAL_NCM_TEXT`;
- `ANALYST_APPROVED_CATALOG`;
- `TECHNICAL_EVIDENCE`.

Regras de transição:

- texto do XML ou descrição oficial isolados chegam no máximo a
  `INCONCLUSIVE`;
- `REVIEW_REQUIRED` exige regra semântica determinística, versionada e aprovada
  pelo analista; ela pode indicar incompatibilidade, nunca sugerir novo NCM;
- catálogo Produto × NCM `APROVADO` pode produzir os estados confirmados;
- `ANALYST_CONFIRMED_MISMATCH` preserva a restrição atual por item;
- `REVIEW_REQUIRED` é observação e não impede UC-003;
- nenhum estado define benefício IBS/CBS.

### Estratégia semântica desta entrega

- Não introduzir chamada externa, LLM ou API durante análise.
- Validar primeiro se o NCM informado existe e está vigente no snapshot oficial
  da competência.
- Normalizar a descrição para triagem local, removendo apenas pontuação, unidades
  e espaços redundantes; preservar o texto original no JSONL local.
- A comparação com o texto oficial serve para registrar suporte descritivo e
  ordenar a fila, não para sugerir novo NCM nem confirmar incompatibilidade.
- Não usar limiar numérico de similaridade como confirmação.
- Sem ruleset semântico aprovado, o resultado permanece `INCONCLUSIVE`.
- O vocabulário de alta precisão deve ser um ruleset versionado e aprovado pelo
  analista, nunca heurística oculta.
- NCM de oito dígitos inexistente ou sem vigência na competência recebe
  `UNVERIFIABLE`, razão `NCM_NOT_EFFECTIVE`, e restringe somente o item por
  evidência objetiva.

## Artefatos locais da triagem

Criar somente quando houver produtos:

```text
04_CONTEUDO/
├── fila-revisao-ncm-descricao.csv
└── ncm-description-review.local.jsonl
```

A fila deve conter referências pseudonimizadas e os campos necessários ao
analista. Descrição integral, ficha técnica e evidência comercial permanecem no
JSONL local. Nenhum desses arquivos entra no Git ou na conversa.

Uma decisão formal futura poderá usar:

```text
00_CONTROLE/revisao-ncm-produtos.csv
item_ref;resultado;ncm_confirmado;status;aprovado_por;evidence_ref;observacao
```

`resultado` aceita `MATCH` ou `MISMATCH`; somente `status=APROVADO`, responsável
e evidência preenchidos produzem estado confirmado.

Esta entrega não deve reescrever XML, NCM informado ou catálogo existente.

O `natOp` de NF-e/NFC-e é copiado do nível documental para os registros de
produto e passou a participar da assinatura determinística da fila de
aquisições. A mudança apenas preserva evidência; não transforma `natOp` em
classificação fiscal.

## Correção de transparência das entradas excluídas

Após a implementação do plano, o UC-003 passou a publicar
`excluded_operation_summary` por motivo CFOP. A população detalhada continua
restrita à pasta local, mas o resumo e o relatório mostram o valor dos
documentos distintos e quantos documentos e itens foram excluídos por devolução
de venda, remessa, retorno ou anulação. O total monetário é contado uma vez e
não é rateado entre motivos. Essa correção elevou o contrato de aquisições
para `1.5.0`, o status de planejamento para `1.9.0` e o lote para `1.11.0`.

## Mix de produtos por fornecedor

O UC-003D também grava `fornecedores-produtos.local.jsonl`, uma linha por
fornecedor e competência, relacionando `NOME EMPRESA + CNPJ`, regime documental,
produtos elegíveis, quantidade, valor e participação no total de produtos. O
resumo público expõe somente esses totais agregados por regime; o detalhamento
identificado é produzido apenas no relatório local solicitado pelo analista.
Essa extensão elevou `COUNTERPARTY_SCHEMA_VERSION` para `1.2.0` e
`DOCUMENTARY_SUMMARY_SCHEMA_VERSION` para `1.1.0`.

## Migração e coerência

Ao implementar os contratos:

- `CONTENT_SCHEMA_VERSION`: `1.4.0`;
- `ACQUISITION_SCHEMA_VERSION`: `1.5.0`;
- `REVENUE_SCHEMA_VERSION`: `1.4.0`;
- `COUNTERPARTY_SCHEMA_VERSION`: `1.2.0`;
- `DOCUMENTARY_SUMMARY_SCHEMA_VERSION`: `1.1.0`;
- `PLANNING_STATUS_SCHEMA_VERSION`: `1.9.0`;
- `BATCH_SCHEMA_VERSION`: `1.11.0`.
- `CREDIT_PLANNING_SCHEMA_VERSION`: `1.0.0`.

Atualizar `_outputs_coherent`, os checks do coordenador e os IDs materiais. Os
loaders também conferem cada hash com o digest confiável embarcado; uma alteração
local resulta em `ValidationError` até a atualização explícita do plugin. Saídas
anteriores devem ser reprocessadas; não criar migração silenciosa de JSON.

## Arquivos previstos

Motor:

- `engine/src/fiscal_document_intake/acquisition.py`;
- `engine/src/fiscal_document_intake/content.py`;
- `engine/src/fiscal_document_intake/operation_classification.py`;
- `engine/src/fiscal_document_intake/revenue.py`;
- `engine/src/fiscal_document_intake/planning_status.py`;
- `engine/src/fiscal_document_intake/portfolio_batch.py`;
- `engine/src/fiscal_document_intake/credit_planning.py`;
- `engine/src/fiscal_document_intake/cli.py` e launchers, se os novos locks
  exigirem argumentos adicionais.

Testes:

- `engine/tests/test_uc002.py`;
- `engine/tests/test_uc003.py`;
- `engine/tests/test_uc003_revenue.py`;
- `engine/tests/test_planning_status.py`;
- `engine/tests/test_portfolio_batch.py`.

Skills e documentação:

- `skills/extrair-conteudo-fiscal/`;
- `skills/revisar-aquisicoes/`;
- `skills/revisar-receitas/`;
- `skills/planejar-reforma-tributaria/`;
- `README.md`, `AGENTS.md` e `docs/PLANO-DE-CONCLUSAO.md`.

## Matriz mínima de testes

### Compras documentais

1. NF-e de entrada usa `vNF`, não soma de `vProd`.
2. NFS-e tomada e CT-e tomado entram em subtotais próprios.
3. Documento duplicado conta uma vez.
4. Cancelado, inválido, fora de período e restrito não entram.
5. Compra sem crédito ou sem natureza aprovada continua no total.
6. Devolução de venda recebida não é classificada como compra.
7. Remessa, retorno e transferência de entrada ficam fora do total confirmado.
8. Documento misto vai para `pending_purchase_treatment`, sem rateio.
9. Ausência de compras produz `0.00` somente após população documental apurada.
10. `category_amounts` mantém semântica de itens.
11. Nenhum CNPJ, chave ou descrição aparece no resumo público.

### Devoluções e comparação

1. Devolução de compra emitida reduz apenas o candidato líquido de compras.
2. Devolução de venda recebida reduz apenas o candidato líquido de receita.
3. Comparação usa mesmo estabelecimento e competência.
4. Receita zero gera razão `null`.
5. A razão usa candidatos líquidos e quatro casas decimais.
6. Frente ausente ou documento pendente gera `PARTIAL`, sem inventar zero.
7. O comparativo não altera `revenue_population_ready`, gates de aquisições ou
   `uc004_planning_authorized`.
8. Relatório deixa claro “auditoria”, “documental” e ausência de vínculo econômico
   entre documentos.

### NCM × descrição

1. NCM ausente/malformado mantém a restrição objetiva existente.
2. NCM inexistente ou fora de vigência no snapshot gera restrição objetiva apenas
   para o item.
3. Descrição genérica permanece `INCONCLUSIVE`.
4. Baixo suporte descritivo sem ruleset aprovado permanece `INCONCLUSIVE`.
5. Regra semântica aprovada pode gerar `REVIEW_REQUIRED`, nunca confirmação.
6. Catálogo aprovado igual confirma correspondência.
7. Catálogo aprovado divergente confirma mismatch e restringe somente o item.
8. Outros itens e outras famílias continuam.
9. Nenhum benefício, crédito ou alíquota é inferido.
10. Resultado é determinístico e não usa rede.
11. Descrições permanecem em artefatos locais.

### Migração e lote

1. Schemas antigos provocam reprocessamento.
2. IDs mudam quando totais, snapshot ou decisão material mudam.
3. Período sem mudança é reaproveitado após nova baseline.
4. Falha de uma competência continua isolada.

## Critérios de aceite

- Todos os testes atuais e novos passam.
- Ruff e `uv lock --check` passam.
- Validadores oficiais das skills e do plugin passam.
- Base sintética comprova todos os estados.
- Homologação real usa somente pasta explicitamente indicada e não copia dados para
  o repositório.
- O relatório apresenta compras totais e comparação sem concluir crédito, margem,
  benefício ou irregularidade.
- Triagem por descrição nunca modifica NCM nem bloqueia sem confirmação aprovada.
- Cachebuster é atualizado pelo helper oficial e o plugin reinstalado.
- Commit e push permanecem sujeitos a autorização explícita.

## Ordem recomendada de implementação

1. Testes e classificador CFOP compartilhado para entradas e saídas.
2. Separação de compras, devoluções de venda e entradas sem compra.
3. Implementação dos totais no UC-003A.
4. Exposição separada da devolução de compra no UC-003B.
5. Comparativo no coordenador.
6. Snapshot NCM vigente e testes de validade.
7. Triagem NCM × descrição não bloqueante.
8. Filas locais e decisão aprovada.
9. Migração de schemas e lote incremental.
10. Documentação, validação, cachebuster e reinstalação.

## Estratégia de commits

1. `refactor: share CFOP operation classification`
2. `feat: add documentary purchase totals`
3. `feat: compare documentary purchases and revenue`
4. `feat: add nonblocking NCM description triage`
5. `docs: finalize purchase and NCM review contracts`

Não misturar aplicação material da LC 214 ou cálculo de crédito nesses commits.

## Handoff para a próxima etapa

Ao retomar:

1. confirme o schema e os hashes dos snapshots antes de uma nova alteração;
2. não altere o significado atual de `category_amounts` sem migração explícita;
3. implemente primeiro os testes de compras documentais;
4. use apenas fontes oficiais primárias para o snapshot NCM;
5. mantenha triagem semântica não bloqueante;
6. não execute dados reais até a suíte sintética passar;
7. ao homologar, relate totais e estados agregados, sem descrições ou
   identificadores fiscais.
