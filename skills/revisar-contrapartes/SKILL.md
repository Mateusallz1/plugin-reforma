---
name: revisar-contrapartes
description: Apura fornecedores, clientes CNPJ e vendas para CPF depois da validação documental, preservando identificadores somente em artefatos locais. Use para preparar a análise de regime do Simples; não use para concluir crédito, débito ou regularidade.
---

# Revisar contrapartes e regime

Execute depois que o UC-001 tiver produzido `03_SAIDAS/validation-result.json`
vigente e autorizado. A apuração usa somente documentos incluídos e autorizados
na pasta indicada.

Na execução direta, a pasta também precisa conter `00_CONTROLE/escopo.json`,
que define os CNPJs próprios. No processamento por carteira, o lote repassa a
identidade já validada em `.reforma-tributaria/configuracao-lote.local.json`;
nesse modo não é necessário duplicar o `escopo.json` em cada competência.

## Caminho rápido

1. Execute `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-counterparty-review.ps1 -Folder <pasta>`.
2. Leia os resumos públicos em `05_REVISAO_AQUISICOES/fornecedores-regime-summary.json` e `06_REVISAO_RECEITAS/clientes-cnpj-regime-summary.json`.
3. Use os JSONL locais somente para a apuração autorizada do analista; não copie CNPJ, nomes ou CPF para a conversa.
4. Acrescente `-MeetingReport` somente quando o analista solicitar um relatório local identificado para reunião com o cliente.

## Regras

- Fornecedores são agrupados por CNPJ e competência. CRT `1`, `2` e `4` indicam opção documental pelo Simples; CRT `3` indica regime normal no documento. Evidências conflitantes permanecem explícitas.
- Clientes CNPJ são agrupados por CNPJ e podem usar um snapshot local de situação do Simples informado com `-SimplesRegistry`. Sem esse snapshot, o motor preserva `UNKNOWN` até a consulta autorizada.
- Vendas para CPF são somente contadas por documento fiscal único; CPF e nome não são persistidos.
- Consumidor sem CPF ou CNPJ fica em subtotal separado, sem agrupamento por nome.
- Valores usam o total do documento validado pelo UC-001; não são somados por item.
- O relatório de reunião é confidencial, local e gerado sob demanda. Ele não é autoridade tributária nem substitui a validação do analista.

Leia [references/simples-registry.schema.md](references/simples-registry.schema.md)
quando precisar preparar o snapshot local de situação do Simples.

## Saídas

```text
05_REVISAO_AQUISICOES/
├── fornecedores-regime-summary.json
└── fornecedores-regime.local.jsonl
06_REVISAO_RECEITAS/
├── clientes-cnpj-regime-summary.json
└── clientes-cnpj-regime.local.jsonl
09_APRESENTACAO_CLIENTE/
└── contrapartes-regime.local.md  # somente com -MeetingReport
```
