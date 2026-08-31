# Contexto operacional do plugin

## Autoridade atual

- O fluxo ativo começa em `validar-base-documental` (UC-001), segue para `extrair-conteudo-fiscal` (UC-002) e para as frentes `revisar-aquisicoes` e `revisar-receitas` do UC-003, com motor Python compartilhado e gerenciado por `uv`.
- A validação documental grava `validation-result.json` e `relatorio-prontidao-documental.md` na pasta do cliente.
- As etapas gravam artefatos em `03_SAIDAS/`, `04_CONTEUDO/`, `05_REVISAO_AQUISICOES/` e `06_REVISAO_RECEITAS/`. Arquivos `*.local.jsonl` contêm detalhes comerciais e devem permanecer locais e restritos.
- O motor compartilhado fica em `engine/`; `scripts/invoke-engine.ps1` é a única autoridade para preparar o ambiente `uv` e executar o CLI.
- O MCP não faz parte do runtime ativo. O legado está preservado em `legacy/mcp/` apenas para consulta e migração futura.
- Não executar, editar ou reativar arquivos de `legacy/mcp/` durante uma análise normal.

## Escopo homologado

- NF-e e NFC-e com direção `ENTRADA`/`SAIDA`.
- NFS-e ABRASF com direção `NFSE_PRESTADOS`/`NFSE_TOMADOS`.
- CT-e modelo 57, leiaute 4.00, com direção `CTE_PRESTADOS`/`CTE_TOMADOS`.
- PDFs auxiliares: DANFE, DACTE, impressões de NFS-e e livros fiscais.
- Autorização por escopo: uma família restrita não invalida famílias independentes prontas.
- Grupos sem ocorrência ficam `SEM_MOVIMENTACAO` e não geram análise operacional.
- Relatórios usam `report_population_policy=COMPLEMENTARY`: divergências são avisos, XML válido não é filtrado e nota declarada sem XML não é incluída. Não implemente `WHITELIST` sem solicitação explícita e novos testes.
- O UC-002 extrai `PRODUCT`, `SERVICE` e `TRANSPORT` somente quando `authorized_for_planning=true` e `operational_analysis_required=true` no UC-001.
- Observações do UC-002 não impedem o UC-003; use `uc003_analysis_authorized` como gate operacional e preserve `lcp214_classification_ready` apenas como indicador de completude.
- Produto com NCM ausente/malformado ou divergente de catálogo `APROVADO` fica restrito por item; não bloqueie serviços, transportes ou outros produtos elegíveis.
- Sem catálogo Produto × NCM ou sem correspondência por `cProd`, registre inconclusão e permita avanço provisório. Não confirme incompatibilidade por similaridade textual.
- O UC-003 revisa somente entradas e não infere natureza econômica ou direito a crédito. Decisões exigem `status=APROVADO` no arquivo local do analista.
- Antes de usar a tabela CST/cClassTrib, confira a publicação oficial atual. Divergência de versão exige manutenção explícita do snapshot e nova bateria de testes.
- A revisão de receitas usa o total do documento, direção e CFOP. CFOP de venda em entrada continua sendo compra; remessa, retorno, anulação e devolução de compra ficam fora da receita operacional.
- Checklist do analista complementa a tabela CFOP oficial e não é exaustivo. `ind_excluded_ibs_cbs` não equivale sozinho a operação sem receita.

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

Leia [docs/PLANO-DE-CONCLUSAO.md](docs/PLANO-DE-CONCLUSAO.md) antes de iniciar uma nova alteração. O próximo incremento funcional é o UC-003: aplicar regras versionadas da LC 214 sobre a população normalizada, mantendo evidência, vigência e aprovação do analista separadas da extração.

## Git e mudanças externas

- Branch principal: `main`.
- Repositório remoto: `https://github.com/Mateusallz1/plugin-reforma.git`.
- Não fazer force push, apagar histórico, criar remoto ou alterar dados de cliente sem autorização explícita.
- Staging deve usar caminhos explícitos; commits devem ser pequenos e descritivos.
