# Base local de produtos por fornecedor

`05_REVISAO_AQUISICOES/fornecedores-produtos.local.jsonl` contém uma linha por
fornecedor e competência. É um artefato identificado e restrito ao analista.

Cada linha preserva:

- `name_cnpj`: apresentação obrigatória no formato `NOME EMPRESA + CNPJ`;
- `simples_status`: situação documental derivada do CRT dos documentos ou do
  snapshot autorizado;
- `document_total`: total dos documentos do fornecedor;
- `product_total` e `share_of_portfolio_products`: valor dos produtos elegíveis e
  participação no total da competência;
- `products`: agrupamento por código do produto, NCM e descrição, com quantidade,
  valor e participação dentro do fornecedor.

O recorte inclui somente linhas `PRODUCT`, de entrada, elegíveis no UC-003 e com
`purchase_operation_status=PURCHASE_CONTEXT`. Serviços, transportes, remessas e
operações pendentes permanecem nos artefatos próprios e não entram no ranking de
produtos.

O resumo público mantém somente totais por regime em `product_mix`. Nomes, CNPJs,
descrições e a composição detalhada não devem ser copiados para o Git nem para a
conversa sem solicitação explícita do analista. A participação serve para
priorizar conferência de CST, cClassTrib e demais evidências; não comprova direito
automático a crédito.
