---
name: conciliar-faturamento-simples
description: Concilia a receita documental pronta do UC-003B com a declaração PGDAS-D por competência, estabelecimento e atividade, separando divergência real de cobertura parcial. Use para empresas do Simples Nacional depois de revisar-receitas; não use para presumir não emissão, comprovar pagamento do DAS ou concluir IBS/CBS.
---

# Conciliar faturamento do Simples

Execute o UC-003C somente quando `06_REVISAO_RECEITAS/revenue-summary.json` indicar `revenue_population_ready=true` e o analista fornecer explicitamente a pasta dos PDFs do PGDAS-D da mesma competência. Receita documental igual a zero é população válida: competência sem nota fiscal deve ser conciliada, não pulada.

## Caminho rápido

1. A partir da raiz desta skill, execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-simple-reconciliation.ps1 -Folder <pasta empresarial> -PgdasFolder <pasta PGDAS-D>`.
2. Leia `07_CONCILIACAO_SIMPLES/simple-reconciliation-summary.json`, `pgdas-lock.json` e `relatorio-conciliacao-simples.md`.
3. Para código de saída `0`, informe se o estabelecimento documental conciliou e se a cobertura do grupo está completa. Cobertura parcial não invalida um estabelecimento conciliado.
4. Para código `2`, apresente as divergências do estabelecimento coberto e pare antes do UC-004.
5. Para outro código, artefato ausente ou ilegível, diagnostique a falha operacional e consulte [references/uc-003c.md](references/uc-003c.md) somente no ponto necessário.

## Regras

- Use a declaração oficial PGDAS-D como autoridade dos valores declarados. Recibo e extrato confirmam a transmissão; DAS gerado não comprova pagamento; relatórios do sistema contábil são auxiliares.
- Concilie primeiro por estabelecimento e atividade. Não compare o total consolidado de matriz e filiais com uma base documental de apenas um estabelecimento.
- `PARTIAL_GROUP_COVERAGE` exige documentos dos estabelecimentos ausentes, mas não transforma a receita descoberta em não emissão.
- Ausência de documento nunca é ausência de movimento. `NO_MOVEMENT` só pode ser afirmado quando documentação e declaração são zero; declaração positiva sem documento é `DECLARED_WITHOUT_DOCUMENT_SUPPORT`.
- `DECLARED_WITHOUT_DOCUMENT_SUPPORT` significa somente que o suporte não foi localizado na base fornecida. Registre `NON_ISSUANCE_CONFIRMED` apenas após decisão expressa e evidenciada do analista em evolução própria desse contrato.
- Preserve valores e registros detalhados em `simple-reconciliation-items.local.jsonl` e `fila-conciliacao-simples.csv`. Não reproduza CNPJ, CPF, recibo, autenticação, IP, certificado ou conteúdo integral dos PDFs na conversa.
- Diferenças por dedução, devolução, caixa, competência ou declaração retificadora permanecem pendentes até evidência e revisão humana.
- Quando a declaração indicar regime `CAIXA`, o resultado publica o aviso `REVENUE_REGIME_CAIXA`. É um alerta não bloqueante: a comparação documental exige análise temporal específica.
- O UC-003C não conclui tributação de IBS/CBS e mantém `uc004_planning_authorized=false`.
- Regras de reconhecimento de faturamento com vigência a partir de 2027 não devem ser aplicadas retroativamente a competências de 2026.

Leia [references/uc-003c.md](references/uc-003c.md) para explicar fontes, estados, saídas, gates e limitações.
