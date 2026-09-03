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
2. Leia os resumos públicos em `05_REVISAO_AQUISICOES/fornecedores-regime-summary.json` e `06_REVISAO_RECEITAS/clientes-cnpj-regime-summary.json`, incluindo o bloco agregado `product_mix`.
3. Use os JSONL locais somente para a apuração autorizada do analista; a base de produtos por fornecedor é detalhada e identificada, mas não deve ser reproduzida na conversa sem solicitação explícita.
4. O identificador de apresentação segue sempre `NOME EMPRESA + CNPJ`; o regime do fornecedor permanece separado entre `OPTANTE_SIMPLES`, `MEI`, `NAO_OPTANTE_SIMPLES`, `REGIME_INDETERMINADO` e evidências divergentes.
5. Acrescente `-MeetingReport` somente quando o analista solicitar um relatório local identificado para reunião com o cliente.

## Regras

- Fornecedores são agrupados por CNPJ e competência. CRT `1` e `2` indicam opção documental pelo Simples, CRT `3` indica regime normal e CRT `4` indica MEI. CRT ausente ou inválido produz `REGIME_INDETERMINADO`; evidências conflitantes permanecem explícitas. `MEI` é compatível com o registro `OPTANTE_SIMPLES` por pertencer à mesma família, e o status mais específico `MEI` é preservado.
- A evidência de CRT é resolvida no nó do documento correspondente à chave fiscal. Em arquivos com mais de um documento, o fallback não escolhe o primeiro emitente da raiz; sem correspondência segura, a evidência permanece ausente.
- Clientes CNPJ são agrupados por CNPJ e podem usar um snapshot local de situação do Simples informado com `-SimplesRegistry`. Sem esse snapshot, o motor preserva `UNKNOWN` até a consulta autorizada.
- Vendas para CPF são somente contadas por documento fiscal único; CPF e nome não são persistidos.
- Consumidor sem CPF ou CNPJ fica em subtotal separado, sem agrupamento por nome.
- Valores usam o total do documento validado pelo UC-001; não são somados por item.
- No resumo de fornecedores, `documentary_entries` é a soma de todos os documentos
  de entrada por contraparte CNPJ (`ALL_ENTRY_DOCUMENT_TOTAL`). Esse valor é uma
  população de contrapartes e não é sinônimo de compras.
- `purchase_context_documents` usa documentos únicos classificados como
  `PURCHASE_CONTEXT`; `purchase_context_items` usa subtotal de itens. O campo
  `eligible_item_total` restringe os itens elegíveis ao UC-003. As bases devem ser
  comparadas somente quando o `amount_basis` for o mesmo.
- Produtos adquiridos são agrupados por fornecedor e competência a partir das linhas `PRODUCT` elegíveis do UC-003. O ranking usa o valor dos itens e publica a participação do fornecedor no total de produtos.
- A base identificada de produtos fica em `fornecedores-produtos.local.jsonl`; ela não altera o total documental de compras nem conclui direito a crédito.
- O relatório de reunião é confidencial, local e gerado sob demanda. Ele não é autoridade tributária nem substitui a validação do analista.

Leia [references/simples-registry.schema.md](references/simples-registry.schema.md)
quando precisar preparar o snapshot local de situação do Simples.
Leia [references/fornecedor-produtos.schema.md](references/fornecedor-produtos.schema.md)
quando o analista solicitar o ranking ou o detalhamento de produtos por fornecedor.

## Saídas

```text
05_REVISAO_AQUISICOES/
├── fornecedores-regime-summary.json
├── fornecedores-regime.local.jsonl
└── fornecedores-produtos.local.jsonl
06_REVISAO_RECEITAS/
├── clientes-cnpj-regime-summary.json
└── clientes-cnpj-regime.local.jsonl
09_APRESENTACAO_CLIENTE/
├── contrapartes-regime.local.md  # somente com -MeetingReport
└── fornecedores-produtos.local.md  # somente com -MeetingReport
```
