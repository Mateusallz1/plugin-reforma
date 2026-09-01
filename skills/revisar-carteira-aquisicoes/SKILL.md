---
name: revisar-carteira-aquisicoes
description: Consolida e aprova classificações pendentes de aquisições em várias empresas, reutilizando decisões somente no alcance confirmado pelo analista. Use quando o analista quiser revisar uma carteira, reduzir classificações repetidas ou retomar aprovações em lote; não use para inferir finalidade econômica, direito a crédito ou ampliar silenciosamente o alcance de uma decisão.
---

# Revisar a carteira de aquisições

Use esta skill para conduzir a revisão pela conversa. A base SQLite e os relatórios permanecem na pasta local da carteira; a planilha é apenas uma exportação opcional.

## Entrada

1. Peça a raiz da carteira somente se ela ainda não tiver sido informada.
2. Use exclusivamente essa raiz. Não procure empresas em diretórios pais ou vizinhos.
3. Para listar a fila, execute:

   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-portfolio-review.ps1 -Action List -PortfolioFolder <pasta>`

4. Apresente grupos em páginas de até dez, informando referência, tipo, número de empresas, ocorrências, valor documental e naturezas permitidas. Os detalhes comerciais ficam no relatório local indicado pelo comando.

## Aprovação

Uma aprovação exige manifestação clara do analista sobre:

- referência do grupo;
- natureza;
- alcance `ITEM`, `COMPANY` ou `PORTFOLIO`;
- identificação do responsável.

Antes de executar, diga quantas empresas e ocorrências serão afetadas. Não transforme uma sugestão, pergunta ou pedido de explicação em aprovação.

Execute:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-portfolio-review.ps1 -Action Approve -PortfolioFolder <pasta> -GroupId <grupo> -Nature <natureza> -Scope <alcance> -ApprovedBy <responsável>`

Para `COMPANY`, acrescente `-CompanyRef <empresa>`. Para `ITEM`, acrescente `-OccurrenceRef <ocorrência>`. Use `-Note <justificativa>` quando fornecida.

Depois da aprovação, liste novamente a fila. Informe somente o resultado, o impacto e a próxima pendência útil.

## Exportação

Gere CSV apenas quando solicitado:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-portfolio-review.ps1 -Action Export -PortfolioFolder <pasta>`

## Limites

- Não classifique a finalidade econômica sem decisão humana.
- Não escolha `PORTFOLIO` por padrão; o alcance deve ser explícito.
- Mudança em descrição, código, NCM, CFOP ou demais campos da assinatura cria outro grupo.
- Não exponha caminhos empresariais, CNPJ, chaves fiscais ou descrições desnecessárias na resposta normal.
- Aprovação operacional não conclui direito a crédito, incidência ou conformidade tributária.
