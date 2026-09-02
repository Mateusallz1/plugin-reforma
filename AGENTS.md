# Contexto operacional do plugin

## Autoridade atual

- A porta de entrada para uma empresa e uma competência é `planejar-reforma-tributaria`. Para várias competências, `processar-periodos-carteira` executa o lote incremental. Para a revisão central, `revisar-carteira-aquisicoes` consolida pendências e registra aprovações com alcance explícito. As skills UC-001 a UC-003C permanecem como componentes operacionais.
- A validação documental grava `validation-result.json` e `relatorio-prontidao-documental.md` na pasta do cliente.
- As etapas gravam artefatos em `03_SAIDAS/`, `04_CONTEUDO/`, `05_REVISAO_AQUISICOES/`, `06_REVISAO_RECEITAS/`, `07_CONCILIACAO_SIMPLES/` e `08_STATUS_PLANEJAMENTO/`. Arquivos `*.local.jsonl` contêm detalhes comerciais e devem permanecer locais e restritos.
- O motor compartilhado fica em `engine/`; `scripts/invoke-engine.ps1` é a única autoridade para preparar o ambiente `uv` e executar o CLI.
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
- A fila central usa somente a raiz de carteira indicada pelo usuário. `ITEM`, `COMPANY` e `PORTFOLIO` são alcances distintos; nunca escolha ou amplie `PORTFOLIO` silenciosamente.
- O lote mantém cada estabelecimento e competência isolados. O manifesto local deve reaproveitar períodos sem mudança, continuar diante de falha parcial e reprocessar somente entradas alteradas ou quando `force` for explicitamente solicitado.
- A reutilização incremental exige hash de conteúdo e coerência dos schemas e IDs das saídas. Presença de arquivo, tamanho e `mtime` não são evidência suficiente.
- `.reforma-tributaria/` contém estado privado da carteira e deve permanecer ignorada pelo Git. Resultados públicos retornam somente referências relativas, nunca caminhos empresariais absolutos.
- Antes de usar a tabela CST/cClassTrib, confira a publicação oficial atual. Divergência de versão exige manutenção explícita do snapshot e nova bateria de testes.
- A revisão de receitas usa o total do documento, direção e CFOP. CFOP de venda em entrada continua sendo compra; remessa, retorno, anulação e devolução de compra ficam fora da receita operacional.
- A composição de `vNF` usa os totais declarados em `ICMSTot`/`ISSQNtot`, conferidos contra `vProd` e `indTot` dos itens. Não some valores de item e totais do documento duas vezes; resíduo não explicado mantém a revisão pendente.
- Checklist do analista complementa a tabela CFOP oficial e não é exaustivo. `ind_excluded_ibs_cbs` não equivale sozinho a operação sem receita.
- O UC-003C usa a declaração PGDAS-D como autoridade, concilia primeiro por estabelecimento e atividade e preserva cobertura parcial. Ausência de suporte documental não comprova não emissão; `non_issuance_confirmed` permanece falso sem decisão humana expressa.
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
