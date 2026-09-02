---
name: processar-periodos-carteira
description: Processa várias competências fiscais de uma carteira em um único lote incremental, preservando resultados separados por estabelecimento e período. Use quando o usuário indicar uma raiz com vários meses ou pedir processamento histórico; não use para misturar competências, ampliar a pasta autorizada ou repetir períodos sem mudança.
---

# Processar períodos da carteira

Esta skill executa o fluxo documental e operacional em lote. Cada competência continua sendo analisada e gravada separadamente.

## Entrada

1. Peça somente a raiz da empresa ou carteira se ela ainda não tiver sido indicada.
2. Use exclusivamente essa raiz. Não procure períodos em diretórios pais ou vizinhos.
3. Se o usuário quiser apenas conferir o lote, execute:

   `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-portfolio-batch.ps1 -Action Plan -PortfolioFolder <pasta>`

4. Informe quantas competências fiscais foram encontradas. Pastas do Simples são fontes de conciliação e não contam como competências fiscais independentes.

### Nomenclatura obrigatória

Cada pasta de competência que contenha XML deve usar exatamente `MM-AAAA` ou
`AAAA-MM` (por exemplo, `01-2026` ou `2026-01`). Formatos como `01.2026`,
`Janeiro-2026` ou nomes de mês por extenso não são reconhecidos. O lote informa
quantas pastas com XML foram ignoradas por nomenclatura inválida; se nenhuma
competência válida restar, a execução termina pedindo a renomeação.

Para procurar PGDAS-D, o lote considera somente `<raiz>\SN\<nome-da-pasta>` ou
`<raiz>\SN\<competência AAAA-MM>`. Uma pasta do Simples sem XML não é uma
competência fiscal do lote.

## Processamento

Antes da primeira execução da rodada, confirme uma única vez que os snapshots oficiais usados pelas skills de aquisições e receitas continuam vigentes. Não repita essa consulta por competência e não atualize snapshots silenciosamente.

Quando o usuário pedir o processamento, execute:

`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-portfolio-batch.ps1 -Action Process -PortfolioFolder <pasta>`

O motor usa dois trabalhadores por padrão, isola falhas por competência e ignora períodos sem alterações. Use `-Force` somente quando o usuário pedir reprocessamento integral ou quando houver manutenção de regra que exija reconstrução.

## Resposta

Informe somente:

- competências encontradas;
- processadas nesta rodada;
- reaproveitadas sem reprocessamento;
- falhas e o que precisam;
- tempo total;
- quantidade de grupos na fila central.

Não exponha CNPJ, chaves fiscais, hashes, caminhos técnicos ou detalhes comerciais. Diante de falha parcial, não repita as competências concluídas; corrija a entrada necessária e execute o mesmo lote novamente.

## Limites

- Competências nunca são combinadas em uma única apuração.
- A configuração local de estabelecimentos pode conter identificadores fiscais e não deve sair da pasta da carteira.
- O lote não transforma classificação operacional em direito a crédito ou conclusão tributária.
- Ausência documental continua sem comprovar não emissão.
