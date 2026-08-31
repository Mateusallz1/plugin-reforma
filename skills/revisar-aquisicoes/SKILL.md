---
name: revisar-aquisicoes
description: Revisa mercadorias, serviços e transportes adquiridos nos registros elegíveis do UC-002, consolida categorias de compra, valida CST/cClassTrib declarado contra snapshot oficial vigente e gera fila para aprovação do analista. Use depois de extrair-conteudo-fiscal; não use para concluir direito a crédito ou conformidade tributária.
---

# Revisar aquisições

Execute o UC-003 somente quando `04_CONTEUDO/content-summary.json` indicar `uc003_analysis_authorized=true`.

## Fontes antes da execução

1. Consulte as páginas oficiais da legislação da RTC, orientações de 2026 e tabelas vigentes do Portal NF-e.
2. Confirme que a versão e a data da tabela cClassTrib coincidem com o snapshot em `references/snapshots/`.
3. Se a fonte oficial estiver mais recente, não valide pares com o snapshot antigo. Informe `SOURCE_UPDATE_REQUIRED` e trate a atualização do snapshot como manutenção explícita do plugin.

## Caminho rápido

1. Execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-acquisition-review.ps1 -Folder <pasta>`.
2. Leia `05_REVISAO_AQUISICOES/acquisition-summary.json`, `ruleset-lock.json` e `relatorio-revisao-aquisicoes.md`.
3. Informe categorias, valores documentais, evidência IBS/CBS, pendências e gates. Não reproduza os JSONL ou CSV locais na conversa.

## Regras

- Revise somente registros de direção `ENTRADA`: produtos como `PURCHASE_GOODS`, serviços como `PURCHASE_SERVICES` e transportes como `PURCHASE_TRANSPORT`.
- Não suponha a natureza da aquisição. Sem decisão `APROVADO` em `00_CONTROLE/classificacao-aquisicoes.csv`, mantenha `PENDING_ANALYST_CLASSIFICATION`.
- A validação CST/cClassTrib comprova somente que o par declarado existe, estava vigente na competência e é aplicável ao tipo de DF-e no snapshot oficial.
- Nunca converta entrada, par válido ou natureza aprovada em direito automático a crédito.
- Preserve registros restritos pelo UC-002 como `RESTRICTED_INPUT`.
- Mantenha dados comerciais detalhados apenas em `acquisition-items.local.jsonl` e `fila-revisao-aquisicoes.csv`.

Leia [references/uc-003.md](references/uc-003.md) para explicar entradas, saídas ou gates. Leia [references/fontes-oficiais.md](references/fontes-oficiais.md) quando precisar explicar atualização, vigência ou o `ruleset-lock`.
