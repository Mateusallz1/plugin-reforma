# Contexto operacional do plugin

O handoff entre máquinas está em `docs/GUIA-RETOMADA-EM-CASA.md`; consulte-o
antes de retomar o fluxo em casa e confirme a versão do manifesto e o estado do
Git.

## Autoridade atual

- A porta de entrada para uma empresa e uma competência é `planejar-reforma-tributaria`. Para várias competências, `processar-periodos-carteira` executa o lote incremental. Para a revisão central, `revisar-carteira-aquisicoes` consolida pendências e registra aprovações com alcance explícito. A skill `revisar-contrapartes` apura fornecedores, clientes CNPJ e vendas para CPF; `simular-credito-ibs-cbs` executa o UC-004 somente como previsão. As skills UC-001 a UC-004 permanecem como componentes operacionais.
- A validação documental grava `validation-result.json` e `relatorio-prontidao-documental.md` na pasta do cliente.
- As etapas gravam artefatos em `03_SAIDAS/`, `04_CONTEUDO/`, `05_REVISAO_AQUISICOES/`, `06_REVISAO_RECEITAS/`, `07_CONCILIACAO_SIMPLES/`, `08_STATUS_PLANEJAMENTO/` e `10_PLANEJAMENTO_CREDITOS/`. Arquivos `*.local.jsonl` contêm detalhes comerciais e devem permanecer locais e restritos.
- A revisão direta de contrapartes usa `00_CONTROLE/escopo.json`; no modo carteira, deve consumir a identidade validada em `.reforma-tributaria/configuracao-lote.local.json`, sem exigir cópias por competência.
- A base identificada de produtos por fornecedor fica em `fornecedores-produtos.local.jsonl` e usa sempre `NOME EMPRESA + CNPJ`; resumos públicos agregam por regime e não podem expor identidades.
- O UC-004 é exclusivamente uma simulação: receita-base vem do PGDAS-D conciliado, a linha comercial é 20% por período, e as taxas 9%/1% são cenários aprovados, nunca conclusão de crédito legal.
- O motor compartilhado fica em `engine/`; `scripts/invoke-engine.ps1` é a única autoridade para preparar o ambiente `uv` e executar o CLI.
- Somente `planejar-reforma-tributaria` pode ser invocada implicitamente; skills operacionais e `uv` exigem invocação explícita.
- O MCP não faz parte do runtime ativo. O legado está preservado em `legacy/mcp/` apenas para consulta e migração futura.
- Não executar, editar ou reativar arquivos de `legacy/mcp/` durante uma análise normal.

## Escopo homologado

- NF-e e NFC-e com direção `ENTRADA`/`SAIDA`.
- NFS-e ABRASF com direção `NFSE_PRESTADOS`/`NFSE_TOMADOS`.
- CT-e modelo 57, leiaute 4.00, com direção `CTE_PRESTADOS`/`CTE_TOMADOS`.
- PDFs auxiliares: DANFE, DACTE, impressões de NFS-e e livros fiscais.
- Autorização por escopo: uma família restrita não invalida famílias independentes prontas.
- Grupos sem ocorrência ficam `SEM_DOCUMENTO` e não geram análise operacional; essa ausência documental não prova ausência de movimento.
- Relatórios usam `report_population_policy=COMPLEMENTARY`: divergências são avisos, XML válido não é filtrado e nota declarada sem XML não é incluída. Não implemente `WHITELIST` sem solicitação explícita e novos testes.
- O UC-002 extrai `PRODUCT`, `SERVICE` e `TRANSPORT` somente quando `authorized_for_planning=true` e `operational_analysis_required=true` no UC-001.
- Observações do UC-002 não impedem o UC-003; use `uc003_analysis_authorized` como gate operacional e preserve `lcp214_classification_ready` apenas como indicador de completude.
- Produto com NCM ausente/malformado, inexistente ou fora de vigência no snapshot fica restrito por item; divergência de catálogo `APROVADO` também restringe somente o item. Não bloqueie serviços, transportes ou outros produtos elegíveis.
- Sem catálogo Produto × NCM ou sem correspondência por `cProd`, registre inconclusão e permita avanço provisório. Não confirme incompatibilidade por similaridade textual.
- O UC-003 revisa somente entradas e não infere natureza econômica ou direito a crédito. Decisões exigem `status=APROVADO` no arquivo local do analista; a fila central pode materializar esse arquivo a partir de uma aprovação humana registrada em SQLite local.
- O UC-003D usa CRT e/ou snapshot local do Simples para fornecedores e clientes CNPJ. Vendas para CPF são apenas contadas por documento e nenhum CPF é persistido.
- A fila central usa somente a raiz de carteira indicada pelo usuário. `ITEM`, `COMPANY` e `PORTFOLIO` são alcances distintos; nunca escolha ou amplie `PORTFOLIO` silenciosamente.
- O lote mantém cada estabelecimento e competência isolados. O manifesto local deve reaproveitar períodos sem mudança, continuar diante de falha parcial e reprocessar somente entradas alteradas ou quando `force` for explicitamente solicitado.
- A reutilização incremental exige hash de conteúdo e coerência dos schemas e IDs das saídas. Presença de arquivo, tamanho e `mtime` não são evidência suficiente.
- `.reforma-tributaria/` contém estado privado da carteira e deve permanecer ignorada pelo Git. Resultados públicos retornam somente referências relativas, nunca caminhos empresariais absolutos.
- Antes de usar a tabela CST/cClassTrib, confira a publicação oficial atual. Divergência de versão exige manutenção explícita do snapshot e nova bateria de testes.
- O `ruleset-lock` só é válido quando o hash do snapshot/ruleset também coincide com o digest confiável embarcado; não aceite um hash apenas recalculado sobre arquivo editado.
- A revisão de receitas usa o total do documento, direção e CFOP. CFOP de venda em entrada continua sendo compra; remessa, retorno, anulação e devolução de compra ficam fora da receita operacional.
- Na revisão de aquisições, entradas que não são compras permanecem fora da população detalhada, mas devem ser demonstradas no resumo em `excluded_operation_summary`: valor e documentos distintos uma única vez, motivos CFOP em `by_reason` e valores por motivo único; documentos mistos ficam em `mixed_reason_documents`, sem rateio.
- A composição de `vNF` usa os totais declarados em `ICMSTot`/`ISSQNtot`, conferidos contra `vProd` e `indTot` dos itens. Não some valores de item e totais do documento duas vezes; resíduo não explicado mantém a revisão pendente.
- Checklist do analista complementa a tabela CFOP oficial e não é exaustivo. `ind_excluded_ibs_cbs` não equivale sozinho a operação sem receita.
- O UC-003C usa a declaração PGDAS-D como autoridade, concilia primeiro por estabelecimento e atividade e preserva cobertura parcial. Ausência de suporte documental não comprova não emissão; `non_issuance_confirmed` permanece falso sem decisão humana expressa.
- Regime PGDAS-D `CAIXA` gera apenas o aviso não bloqueante `REVENUE_REGIME_CAIXA`; diferenças temporais exigem revisão humana.
- O PGDAS-D de 2026 usa as regras vigentes da competência. Não aplique retroativamente regras de reconhecimento de faturamento com vigência a partir de 2027.
- Respostas normais do coordenador não exibem nomes de gates, códigos de saída, hashes ou pastas técnicas. Traduza pendências em linguagem comum e diga se bloqueiam uma frente, um estabelecimento ou todo o fluxo.

## Privacidade e evidência

- Nunca copie XML, PDF, XLSX, CSV real, CNPJ, CPF, chave fiscal ou credencial para este repositório.
- Dados de clientes permanecem fora do plugin e fora do Git.
- O JSON técnico e a conversa permanecem pseudonimizados; somente o relatório local pode identificar a empresa-alvo.
- `VALID_DOCUMENTARY` é coerência documental local, não consulta atual à autoridade, validação de assinatura ou parecer tributário.

## Como verificar alterações

Execute os comandos Python por `uv`, nunca por `pip` ou por um ambiente manual:

```text
uv run --project engine --group dev pytest engine/tests -q
uv run --project engine --group dev ruff check engine
uv run --project engine --group dev ruff format --check engine
uv lock --project engine --check
```

Antes de empacotar, valide as skills e o plugin com os validadores oficiais. Depois reinstale pelo marketplace pessoal e abra uma nova tarefa do Codex.

## Ordem de trabalho pendente

Leia [docs/PLANO-DE-CONCLUSAO.md](docs/PLANO-DE-CONCLUSAO.md) antes de iniciar uma nova alteração. O incremento de [docs/PLANO-IMPLEMENTACAO-COMPRAS-NCM.md](docs/PLANO-IMPLEMENTACAO-COMPRAS-NCM.md) está implementado: compras documentais totais, comparação não bloqueante com vendas e triagem NCM × descrição sem reclassificação automática. Só depois avance para regras materiais da LC 214, mantendo evidência, vigência e aprovação do analista separadas da extração.

## Git e mudanças externas

- Branch principal: `main`.
- Repositório remoto: `https://github.com/Mateusallz1/plugin-reforma.git`.
- Não fazer force push, apagar histórico, criar remoto ou alterar dados de cliente sem autorização explícita.
- Staging deve usar caminhos explícitos; commits devem ser pequenos e descritivos.
