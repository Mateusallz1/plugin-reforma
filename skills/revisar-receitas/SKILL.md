---
name: revisar-receitas
description: Revisa NF-e/NFC-e de saída, NFS-e prestadas, CT-e prestados, devoluções e remessas; usa o valor total do documento, classifica itens por CFOP e separa receita, ajustes e operações sem receita. Use depois do UC-002; não use para concluir receita tributável ou débito de IBS/CBS.
---

# Revisar receitas

Execute esta fase do UC-003 somente quando o UC-002 indicar `uc003_analysis_authorized=true`.

## Fontes antes da execução

1. Consulte a tabela CFOP vigente no Portal NF-e e confirme versão, publicação e hash do snapshot em `references/snapshots/`.
2. Confirme que o ruleset em `references/rules/` corresponde ao checklist homologado pelo analista.
3. Se a tabela oficial estiver mais recente, informe `SOURCE_UPDATE_REQUIRED` e não classifique com snapshot antigo.

Os loaders também conferem o hash confiável do snapshot CFOP e do ruleset do
analista. Edição local ou arquivo com nome não reconhecido interrompe a revisão.

## Caminho rápido

1. Execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-revenue-review.ps1 -Folder <pasta>`.
2. Leia `06_REVISAO_RECEITAS/revenue-summary.json`, `cfop-ruleset-lock.json` e `relatorio-revisao-receitas.md`.
3. Para código de saída `0`, informe receita documental bruta, devoluções, remessas, pendências, diferenças entre documento e itens e gates.
4. Para código `2`, informe por que a revisão não pode alimentar a etapa seguinte e pare.
5. Para outro código, artefato ausente ou ilegível, diagnostique a falha operacional e consulte [references/uc-003-receitas.md](references/uc-003-receitas.md) somente no ponto necessário.

## Regras

- Use o total do documento do UC-001 como valor: `vNF`, valor do serviço ou valor da prestação.
- Use os itens do UC-002 para explicar e classificar CFOP; nunca some `vProd` como substituto silencioso do total da nota.
- A classificação CFOP de entradas e saídas é compartilhada com o UC-003A; isso evita que devoluções de venda ou remessas de entrada sejam contadas como compras.
- Determine primeiro a direção. CFOP de venda em uma nota de entrada representa venda do fornecedor, não receita da empresa analisada.
- Use `indDevol`, `indRetor`, `indAnula` e `indRemes` do snapshot oficial. O checklist de CFOPs usuais de venda é regra do analista e não lista exaustiva.
- Documento com classes distintas fica `MIXED_DOCUMENT_PENDING_ALLOCATION`.
- Demonstre remessas, retornos, anulações e devoluções de compra fora da receita operacional.
- `net_documentary_revenue_candidate` não é receita tributável nem débito de IBS/CBS.
- Mantenha JSONL e fila CSV somente na pasta local do cliente.

Leia [references/uc-003-receitas.md](references/uc-003-receitas.md) para explicar categorias, saídas e gates. Leia [references/fontes-cfop.md](references/fontes-cfop.md) quando precisar explicar atualização ou o ruleset.
