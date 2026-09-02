---
name: extrair-conteudo-fiscal
description: Extrai e normaliza produtos, serviços e transportes autorizados pelo UC-001, registra observações não bloqueantes e restringe itens com problema Produto × NCM antes do UC-003. Use depois de validar-base-documental; não use para concluir tratamento tributário, crédito ou conformidade legal.
---

# Extrair conteúdo fiscal

Execute o UC-002 somente depois que o UC-001 tiver produzido `03_SAIDAS/validation-result.json` com ao menos um escopo autorizado.

## Caminho rápido

1. A partir da raiz desta skill, execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-content-extractor.ps1 -Folder <pasta>`.
2. Leia `<pasta>\04_CONTEUDO\content-summary.json` e `<pasta>\04_CONTEUDO\relatorio-qualidade-conteudo.md`.
3. Para código `0`, informe cobertura, observações, restrições e os gates `content_extraction_ready`, `uc003_analysis_authorized` e `uc003_full_population_ready`.
4. Para código `2`, informe por que a extração não pode alimentar a etapa seguinte.

`normalized-items.local.jsonl` e `ncm-description-review.local.jsonl` contêm descrições comerciais e são restritos à pasta local do cliente. Use-os como entrada determinística das próximas etapas, mas não reproduza seu conteúdo na conversa. A fila CSV de NCM é apenas uma fila de triagem, não reclassifica o produto.

## Regras

- Extraia somente documentos com `authorized_for_planning=true` e `operational_analysis_required=true` no UC-001.
- Preserve `document_ref`, `item_ref`, `analysis_scope`, `analysis_group`, direção e hash da fonte.
- Mantenha campos ausentes como `null`; nunca converta ausência em zero, isenção ou não incidência.
- Separe CST/CSOSN por tributo e caminho XML. Uma tag genérica `CST` não é evidência suficiente.
- Trate NCM, CFOP, CNAE, NBS e `cClassTrib` como evidências distintas.
- Observações de qualidade não impedem o UC-003. Restrinja somente o item de produto com NCM ausente/malformado, inexistente ou fora de vigência no snapshot, ou divergente de uma entrada `APROVADO` no catálogo do analista.
- Quando existir, leia `00_CONTROLE/catalogo-produtos-ncm.csv`. Sem catálogo ou sem correspondência por `codigo_produto`, registre inconclusão e permita avanço provisório; não compare descrição por palavras para criar bloqueio.
- Preserve serviços, transportes e produtos elegíveis quando outro item estiver restrito.
- O UC-002 valida presença, formato e coerência do conteúdo. Classificação jurídica pertence ao UC-003 e exige regras versionadas e revisão do analista.
- O JSON técnico e a conversa permanecem sem XML bruto, chaves completas, CPF, CNPJ ou identidade de contraparte.

Leia [references/uc-002.md](references/uc-002.md) para explicar o contrato, os gates ou uma falha operacional. Leia [references/campos-conteudo.md](references/campos-conteudo.md) somente quando precisar explicar os campos extraídos ou uma lacuna por modelo documental.
