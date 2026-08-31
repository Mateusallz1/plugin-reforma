# Plano de conclusão da etapa de ajustes

## Baseline atual

- Plugin em desenvolvimento: `0.28.0`; a instalação ativa permanece em `0.26.0+codex.20260831141112` até o próximo commit e cachebuster.
- Branch: `main`; confirme `git status` e `git log -1` ao retomar, sem depender de hash gravado neste documento.
- Runtime ativo: Python/`uv`, sem servidor MCP no manifesto.
- Skills no fonte: `uv`, `validar-base-documental`, `extrair-conteudo-fiscal`, `revisar-aquisicoes` e `revisar-receitas`.
- UC-001: NF-e, NFC-e, NFS-e ABRASF e CT-e modelo 57.
- Esquema de saída UC-001: `1.8.0`, com política de relatório, autorização por escopo e oito grupos operacionais.
- Homologação real: 130 documentos incluídos, três escopos `READY`, sem bloqueadores.
- UC-002: extração normalizada de produtos, serviços e transportes somente nos grupos operacionais autorizados.
- Homologação real do UC-002: 130 documentos selecionados, 204 registros, 25 componentes, 44 NF-e reconciliadas e nenhum bloqueador de extração.
- Testes: 33 aprovados com as revisões de aquisições e receitas; Ruff, formatação e lock do `uv` aprovados.

## Concluído

- [x] Validação inicial de NF-e/NFC-e.
- [x] Inclusão de NFS-e ABRASF consolidada, prestadas e tomadas.
- [x] Inclusão de CT-e modelo 57 e DACTE.
- [x] Separação por modelo e direção.
- [x] Estados `SEM_MOVIMENTACAO` e `MOVIMENTACAO_RESTRITA`.
- [x] Autorizações independentes para `NFE_NFCE`, `NFSE` e `CTE`.
- [x] Fast path operacional.
- [x] Retirada do MCP e da skill legada das rotas ativas.
- [x] Preservação do bundle Node em `legacy/mcp/` com checksum.
- [x] Repositório Git local e remoto pessoal.
- [x] Contexto durável em `AGENTS.md` e `README.md`.
- [x] Skill `uv` disponível somente por invocação explícita.
- [x] Fast path curto e orientado à execução.
- [x] UC-002 com skill própria e gate dependente do UC-001.
- [x] Extração de 118 produtos, 80 serviços e 6 transportes na base real, sem levar dados fiscais ao Git.
- [x] Separação entre `content_extraction_ready` e `lcp214_classification_ready`.
- [x] Observações do UC-002 sem bloqueio do início do UC-003.
- [x] Restrição por item para NCM ausente/malformado ou divergência confirmada Produto × NCM.
- [x] Catálogo opcional homologado pelo analista, sem inferência bloqueante por descrição.
- [x] Política de relatório `COMPLEMENTARY` explícita e retrocompatível; `WHITELIST` reservado para evolução futura.
- [x] UC-003 inicial com separação de mercadorias, serviços e transportes adquiridos.
- [x] Snapshot oficial IT 2025.002 v1.60 com 18 CSTs, 164 pares cClassTrib e hash do XLSX de origem.
- [x] Fila local de classificação e aprovação explícita do analista.
- [x] Validação de par declarado por vigência e aplicabilidade ao tipo de DF-e, sem concluir crédito.
- [x] UC-003B com valor total do documento e classificação das saídas por CFOP.
- [x] Snapshot CFOP IT 2023.002 v2.00, publicado em 25/08/2026, com 619 códigos e hash do XLSX.
- [x] Devoluções e remessas orientadas pelos indicadores oficiais, com checklist do analista separado.

A homologação real da política `COMPLEMENTARY` preservou 130 documentos incluídos e `planning_authorized=true`; sem relatório disponível, `reconciliation_ready=false` e 130 ocorrências `XML_WITHOUT_REPORT` permaneceram como avisos. O UC-002 consumiu o schema 1.8.0 sem regressão e manteve 204 registros elegíveis para o UC-003.

## Ajustes desta fase

### 1. Tornar `uv` explicit-only — concluído em 2026-08-31

`skills/uv/agents/openai.yaml` usa `allow_implicit_invocation: false`. O texto vendorizado da Astral permanece inalterado. A execução do motor continua usando `uv` internamente; somente o roteamento automático da skill deixa de ocorrer.

Resultado: análises normais não carregam a skill `uv`; manutenção explícita do motor continua possível.

### 2. Reescrever o fast path positivamente — concluído em 2026-08-31

O contrato agora orienta:

1. execute o launcher uma vez;
2. leia os dois artefatos em `03_SAIDAS`;
3. respeite `authorized_scopes`, `restricted_scopes` e `operational_analysis_required`;
4. só entre em diagnóstico se o launcher falhar ou os artefatos estiverem ausentes.

O motor, os gates, a privacidade e os códigos de saída permaneceram inalterados.

### 3. Validar a retomada em máquina limpa

Clonar o repositório em outra conta Windows, instalar o plugin local, reiniciar o Desktop e executar uma base sintética. Confirmar que `AGENTS.md`, `README.md` e as referências direcionam o trabalho sem depender da conversa anterior.

Uma simulação local por clone isolado passou nos 14 testes e nos validadores. Ela também identificou normalização indevida de fim de linha no launcher legado; `legacy/mcp/**` passou a ser preservado como bytes opacos. Ainda falta repetir a instalação na máquina de casa.

### 4. UC-002 — extração de conteúdo concluída em 2026-08-31

O UC-002 consome o `validation-result.json`, seleciona somente documentos autorizados e com análise operacional necessária, normaliza os itens e reconcilia o total de produtos das NF-e. Os achados de qualidade permanecem explícitos e não são corrigidos silenciosamente.

Na base real homologada, 80 NFS-e trouxeram código de nove dígitos no campo `CodigoCnae`; o motor preservou o valor e marcou `CNAE_INVALID` para revisão, pois não corresponde ao formato nacional de sete dígitos. A ausência de NBS e cClassTrib também exige revisão, mas não bloqueia a extração.

Na política `1.1.0`, esses achados passam a ser observações e não impedem o UC-003. O avanço é controlado por registro: NCM ausente/malformado restringe o produto e uma divergência somente é confirmada quando `cProd` e NCM diferem de uma entrada `APROVADO` em `00_CONTROLE/catalogo-produtos-ncm.csv`. Sem catálogo, o resultado é inconclusivo e provisoriamente elegível.

A nova homologação real manteve 204 registros: 204 elegíveis, nenhuma restrição e `uc003_analysis_authorized=true`. Foram preservadas 453 observações agregadas — 175 sem `cClassTrib`, 118 sem catálogo Produto × NCM, 80 CNAE fora do formato nacional e 80 sem NBS — sem expor descrições ou identificadores fiscais.

### 5. Homologar o modelo de relatório do analista

Quando o modelo final do cliente estiver disponível, registrá-lo como asset/template versionado e separar claramente:

- dados observados pelo motor;
- regras fornecidas pelo analista;
- hipóteses e premissas;
- conclusão sujeita à aprovação fiscal.

Não colocar o modelo homologado dentro do motor de validação documental.

### 6. UC-003 — revisão inicial das aquisições

O piloto seleciona entradas elegíveis do UC-002, classifica o fluxo como compra de mercadoria, serviço ou transporte, valida CST/cClassTrib declarado no snapshot oficial e gera a fila de naturezas para o analista. O `ruleset-lock.json` torna cada execução reproduzível.

Na homologação real, 204 registros originaram 70 aquisições: 63 mercadorias, 1 serviço tomado e 6 transportes tomados. O snapshot confirmou 29 pares CST/cClassTrib e manteve 41 registros com evidência pendente; todas as 70 naturezas aguardam aprovação do analista.

Ainda falta homologar a fila real e implementar as regras materiais que avaliarão hipóteses de crédito. Até lá, `uc004_planning_authorized=false`.

### 7. UC-003B — revisão inicial das receitas

O piloto combina total documental do UC-001 com CFOPs dos itens do UC-002. Notas mistas ou diferenças entre `vNF` e `vProd` ficam pendentes, sem rateio automático.

Na base real, 29 NF-e de venda somaram R$ 51.345,00 e 79 NFS-e prestadas somaram R$ 66.160,00. A receita operacional documental candidata foi R$ 117.505,00, sem devoluções, remessas, pendências ou componentes não alocados. A população de receita ficou pronta, mas o UC-004 permanece não autorizado.

## Backlog condicional

Só iniciar se houver necessidade real e amostras aprovadas:

- ZIP com limites, deduplicação e origem relativa;
- NFS-e Nacional e distinção entre NFS-e emitida e DPS;
- CT-e OS e eventos de CT-e;
- flag de enriquecimento de regime local;
- perfis de crédito, débito, risco, partes e reconciliação sobre os grupos autorizados.

Esses itens não devem reintroduzir o MCP como autoridade paralela.

## Critérios de encerramento desta etapa

- `mcpServers` ausente do manifesto ativo;
- nenhum legado carregado por `skills/`;
- `uv` sem invocação implícita durante análise normal;
- fast path curto e positivo;
- testes e validadores aprovados;
- base real reproduzível sem dados fiscais no Git;
- README e `AGENTS.md` suficientes para retomar o trabalho em outra máquina;
- relatório final ainda depende de homologação do analista.

## O que não fazer

- não apagar `legacy/mcp/`;
- não copiar XML, PDF, XLSX, CSV real ou credenciais para o repositório;
- não forçar push ou reescrever `main`;
- não tratar validação local como consulta oficial;
- não criar análises operacionais para grupos `SEM_MOVIMENTACAO`;
- não iniciar novas migrações antes de concluir os itens 1–3.
