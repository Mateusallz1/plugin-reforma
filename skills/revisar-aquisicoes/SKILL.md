---
name: revisar-aquisicoes
description: Revisa mercadorias, serviços e transportes adquiridos nos registros elegíveis do UC-002, consolida categorias de compra, valida CST/cClassTrib declarado contra snapshot oficial vigente e gera fila para aprovação do analista. Use depois de extrair-conteudo-fiscal; não use para concluir direito a crédito ou conformidade tributária.
---

# Revisar aquisições

Execute o UC-003 somente quando `04_CONTEUDO/content-summary.json` indicar `uc003_analysis_authorized=true`.

## Fontes antes da execução

1. Consulte as páginas oficiais da legislação da RTC, orientações de 2026 e tabelas vigentes do Portal NF-e.
2. Confirme que a versão e a data das tabelas cClassTrib e CFOP coincidem com os snapshots usados pelo launcher.
3. Se a fonte oficial estiver mais recente, não valide pares ou operações com snapshot antigo. Informe `SOURCE_UPDATE_REQUIRED` e trate a atualização dos snapshots como manutenção explícita do plugin.

## Caminho rápido

1. Execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-acquisition-review.ps1 -Folder <pasta>`; o launcher fixa também o snapshot CFOP e o ruleset de classificação de operações.
2. Leia `05_REVISAO_AQUISICOES/acquisition-summary.json`, `ruleset-lock.json` e `relatorio-revisao-aquisicoes.md`.
3. Para código de saída `0`, informe categorias, valores documentais, evidência IBS/CBS, pendências e gates. Não reproduza os JSONL ou CSV locais na conversa.
4. Para código `2`, informe por que a revisão não pode alimentar a etapa seguinte e pare.
5. Para outro código, artefato ausente ou ilegível, diagnostique a falha operacional e consulte [references/uc-003.md](references/uc-003.md) somente no ponto necessário.

## Regras

- Revise somente registros de direção `ENTRADA`: produtos como `PURCHASE_GOODS`, serviços como `PURCHASE_SERVICES` e transportes como `PURCHASE_TRANSPORT`.
- Nas NF-e/NFC-e, não trate toda entrada como compra: devolução de venda, remessa, retorno, transferência e operação sem compra ficam fora do total confirmado e aparecem como contexto ou pendência.
- O resumo e o relatório demonstram `excluded_operation_summary`: o valor total e a quantidade de documentos distintos aparecem uma única vez, enquanto `by_reason` mostra documentos, itens e valor por motivo quando o documento possui motivo único. A contagem por motivo pode se sobrepor; documentos com motivos múltiplos ficam em `mixed_reason_documents`, sem rateio.
- O total documental de compras usa o `vNF` de cada documento único; `category_amounts` continua sendo subtotal dos itens para análise operacional.
- Não suponha a natureza da aquisição. Sem decisão `APROVADO` em `00_CONTROLE/classificacao-aquisicoes.csv`, mantenha `PENDING_ANALYST_CLASSIFICATION`.
- A validação CST/cClassTrib comprova somente que o par declarado existe, estava vigente na competência e é aplicável ao tipo de DF-e no snapshot oficial.
- O launcher verifica o hash do snapshot CST/cClassTrib, do snapshot CFOP e do ruleset do analista contra os valores confiáveis embarcados; divergência interrompe a execução e exige atualização explícita.
- Nunca converta entrada, par válido ou natureza aprovada em direito automático a crédito.
- Preserve registros restritos pelo UC-002 como `RESTRICTED_INPUT`.
- Mantenha dados comerciais detalhados apenas em `acquisition-items.local.jsonl` e `fila-revisao-aquisicoes.csv`.
- Quando houver várias empresas, encaminhe a aprovação para `revisar-carteira-aquisicoes`; a skill central materializa decisões compatíveis no mesmo arquivo local consumido por este fluxo.

Leia [references/uc-003.md](references/uc-003.md) para explicar entradas, saídas ou gates. Leia [references/fontes-oficiais.md](references/fontes-oficiais.md) quando precisar explicar atualização, vigência ou o `ruleset-lock`.
