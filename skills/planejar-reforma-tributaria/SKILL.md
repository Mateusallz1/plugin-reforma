---
name: planejar-reforma-tributaria
description: Conduz o planejamento da Reforma Tributária a partir de uma pasta empresarial, identifica o que já foi concluído, executa automaticamente as próximas etapas autorizadas e pede ao usuário somente a informação indispensável. Use como porta de entrada ou para retomar o fluxo; não use para ignorar gates, aprovações do analista ou limites de escopo.
---

# Planejar a Reforma Tributária

Esta é a porta de entrada do plugin. O usuário não precisa conhecer UCs, códigos de saída, nomes de gates ou skills operacionais.

## Início

1. Se ainda não houver uma pasta, peça somente a pasta do estabelecimento e da competência que será analisada.
2. Use exclusivamente a raiz indicada. Não procure empresas, filiais ou competências em diretórios vizinhos.
3. Quando a pasta indicada representar uma carteira com vários estabelecimentos ou competências, use `processar-periodos-carteira` em vez de repetir este fluxo mês a mês.
4. Para uma única competência, execute `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-planning-status.ps1 -Folder <pasta>`. Acrescente `-PgdasFolder <pasta PGDAS-D>` somente quando o usuário já a tiver indicado.
5. Leia `08_STATUS_PLANEJAMENTO/planning-status.json` e `relatorio-status-planejamento.md`.

## Continuação automática

Quando `available_actions` trouxer uma ação com `automatic=true`, siga [references/roteamento.md](references/roteamento.md), execute cada etapa no máximo uma vez na mesma rodada e gere novamente o status. Continue enquanto houver uma ação segura e nenhuma entrada indispensável estiver ausente.

Antes de revisar aquisições ou receitas, leia a skill operacional correspondente e cumpra a verificação de fontes oficiais. Não atualize snapshots silenciosamente. A conciliação do Simples exige uma pasta PGDAS-D explicitamente indicada.

Depois de receitas e conciliação, a apuração de contrapartes pode ser executada
automaticamente; seus identificadores permanecem em artefatos locais e o modo de
reunião só é gerado mediante solicitação explícita.

A simulação de crédito IBS/CBS é uma etapa posterior e explícita. Ela só deve ser
executada quando o PGDAS-D estiver conciliado no período ou grupo e o analista
tiver aprovado o cenário de taxas; leia `simular-credito-ibs-cbs` antes de rodá-la.
As saídas operacionais precisam carregar `simulation_authorized=true`; isso não
substitui nem altera `uc004_planning_authorized`, que permanece reservado ao
planejamento fiscal/legal.

Pare quando:

- houver `required_inputs` que dependam do usuário ou do analista;
- a próxima etapa ainda não estiver implementada;
- ocorrer falha operacional;
- uma nova execução repetiria uma ação já tentada nesta rodada.

Quando a pendência for a classificação das aquisições, não exija planilha. Informe que o analista pode consolidar várias empresas pela skill `revisar-carteira-aquisicoes`. Peça a raiz da carteira somente se ele quiser usar esse fluxo; nunca deduza a raiz procurando diretórios vizinhos.

## Resposta ao usuário

Responda sempre nesta ordem e em linguagem comum:

1. **Situação atual**
2. **Resumo documental preliminar**
3. **O que foi concluído**
4. **O que foi encontrado**
5. **Preciso de você**
6. **Por que é necessário**
7. **O que pode continuar**
8. **Próximo passo**

O resumo preliminar deve aparecer sempre que houver dados de uma etapa concluída,
mesmo que outra frente esteja pendente ou bloqueada. Mostre, quando apurados,
quantidades e valores de documentos válidos por entrada/saída e por tipo (NF-e,
NFC-e, NFS-e e CT-e), produtos/serviços/transportes extraídos, categorias
operacionais de aquisições, receitas documentais por componente e a conciliação
com o PGDAS-D. Use “não apurado” quando a fonte ainda não existir; não transforme
ausência de documentos em zero movimento.

Identifique o resumo como evidência observada, parcial ou pendente. A natureza
econômica das aquisições continua dependendo do analista, e valores documentais
não devem ser apresentados como receita tributável, crédito ou débito. Não inclua
descrições comerciais, CNPJ, CPF, chaves fiscais ou outros identificadores no
resumo exibido na conversa.

Não apresente códigos, nomes de gates, hashes ou pastas de saída, salvo se o usuário pedir detalhes técnicos. Explique claramente se a pendência bloqueia apenas um estabelecimento, uma frente de análise ou todo o planejamento.

## Limites

- Observação não bloqueante não vira exigência do usuário.
- Ausência documental não comprova não emissão.
- Classificação automática não substitui aprovação humana quando a regra exigir decisão do analista.
- O ciclo atual cobre empresas do Simples Nacional até a conciliação do PGDAS-D; o UC-004 produz somente simulação de planejamento e não autoriza crédito legal.
- Grupos com vários estabelecimentos permanecem parciais enquanto as respectivas pastas não forem analisadas individualmente.
