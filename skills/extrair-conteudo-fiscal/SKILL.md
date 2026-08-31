---
name: extrair-conteudo-fiscal
description: Extrai e normaliza produtos, serviços e prestações de transporte dos XMLs autorizados pelo UC-001, mede cobertura e gera fila de revisão antes da classificação pela LCP 214. Use depois de validar-base-documental; não use para concluir tratamento tributário, crédito ou conformidade legal.
---

# Extrair conteúdo fiscal

Execute o UC-002 somente depois que o UC-001 tiver produzido `03_SAIDAS/validation-result.json` com ao menos um escopo autorizado.

## Caminho rápido

1. A partir da raiz desta skill, execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-content-extractor.ps1 -Folder <pasta>`.
2. Leia `<pasta>\04_CONTEUDO\content-summary.json` e `<pasta>\04_CONTEUDO\relatorio-qualidade-conteudo.md`.
3. Para código `0`, informe cobertura, blockers, fila de revisão e os gates `content_extraction_ready` e `lcp214_classification_ready`.
4. Para código `2`, informe por que a extração não pode alimentar a etapa seguinte.

`normalized-items.local.jsonl` contém descrições comerciais e é restrito à pasta local do cliente. Use-o como entrada determinística das próximas etapas, mas não reproduza seu conteúdo na conversa.

## Regras

- Extraia somente documentos com `authorized_for_planning=true` e `operational_analysis_required=true` no UC-001.
- Preserve `document_ref`, `item_ref`, `analysis_scope`, `analysis_group`, direção e hash da fonte.
- Mantenha campos ausentes como `null`; nunca converta ausência em zero, isenção ou não incidência.
- Separe CST/CSOSN por tributo e caminho XML. Uma tag genérica `CST` não é evidência suficiente.
- Trate NCM, CFOP, CNAE, NBS e `cClassTrib` como evidências distintas.
- O UC-002 valida presença, formato e coerência do conteúdo. Classificação jurídica pertence ao UC-003 e exige regras versionadas e revisão do analista.
- O JSON técnico e a conversa permanecem sem XML bruto, chaves completas, CPF, CNPJ ou identidade de contraparte.

Leia [references/uc-002.md](references/uc-002.md) para explicar o contrato, os gates ou uma falha operacional. Leia [references/campos-conteudo.md](references/campos-conteudo.md) somente quando precisar explicar os campos extraídos ou uma lacuna por modelo documental.
