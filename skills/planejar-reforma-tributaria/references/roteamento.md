# Roteamento do planejamento

Execute as ações somente dentro da pasta empresarial indicada. Depois de cada ação, gere novamente `planning-status`.

| Ação | Procedimento |
|---|---|
| `RUN_DOCUMENT_VALIDATION` | Leia `../validar-base-documental/SKILL.md` e execute seu launcher. |
| `RUN_CONTENT_EXTRACTION` | Leia `../extrair-conteudo-fiscal/SKILL.md` e execute seu launcher. |
| `RUN_ACQUISITION_REVIEW` | Leia `../revisar-aquisicoes/SKILL.md`, confira as fontes oficiais e execute seu launcher. |
| `RUN_REVENUE_REVIEW` | Leia `../revisar-receitas/SKILL.md`, confira as fontes oficiais e execute seu launcher. |
| `RUN_COUNTERPARTY_REVIEW` | Leia `../revisar-contrapartes/SKILL.md` e execute seu launcher. |
| `RUN_SIMPLE_RECONCILIATION` | Leia `../conciliar-faturamento-simples/SKILL.md` e execute seu launcher com a pasta PGDAS-D indicada. |

## Tradução das entradas necessárias

- `RESOLVE_DOCUMENTARY_BLOCKERS`: peça os documentos corrigidos ou complementares apontados no relatório, sem pedir uma pasta “limpa”.
- `RESOLVE_CONTENT_RESTRICTIONS`: explique quais tipos de item foram restringidos e qual evidência pode corrigi-los.
- `APPROVE_ACQUISITION_CLASSIFICATIONS`: ofereça a fila central da carteira; use a fila local da empresa apenas quando o analista preferir revisão isolada.
- `REVIEW_REVENUE_DIFFERENCES`: peça revisão apenas dos documentos ou valores pendentes.
- `PROVIDE_PGDAS_FOLDER`: peça a pasta que contém a declaração PGDAS-D da competência; recibo e extrato são complementares.
- `REVIEW_SIMPLE_REVENUE_DIFFERENCES`: peça evidência para as diferenças, sem afirmar omissão ou não emissão.
- `PROVIDE_MISSING_ESTABLISHMENT_DOCUMENTS`: peça a pasta fiscal do estabelecimento ausente e explique que o estabelecimento já conciliado pode continuar.

## Prioridade

1. Falha que bloqueia todo o fluxo.
2. Ação automática já autorizada.
3. Entrada que bloqueia somente uma frente.
4. Entrada necessária para o fechamento consolidado.
5. Limitação de funcionalidade ainda não implementada.

Quando houver ações automáticas e entradas humanas ao mesmo tempo, execute primeiro as ações independentes e depois apresente uma única lista consolidada do que precisa do usuário.
