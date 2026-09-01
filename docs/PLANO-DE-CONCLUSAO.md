# Plano de conclusão da etapa de ajustes

## Baseline atual

- Plugin fonte e instalação ativa: `0.28.0`; confira o cachebuster vigente no manifesto, sem tratá-lo como versão funcional separada.
- Branch: `main`; confirme `git status` e `git log -1` ao retomar, sem depender de hash gravado neste documento.
- Runtime ativo: Python/`uv`, sem servidor MCP no manifesto.
- Motor compartilhado em `engine/`, com bootstrap central em `scripts/invoke-engine.ps1`.
- Skills no fonte: `planejar-reforma-tributaria` como porta de entrada, `uv` para manutenção e as skills operacionais de UC-001 a UC-003C.
- UC-001: NF-e, NFC-e, NFS-e ABRASF e CT-e modelo 57.
- Esquema de saída UC-001: `1.9.0`, com política de relatório, autorização por escopo e oito grupos operacionais.
- Homologação real: 130 documentos incluídos, três escopos `READY`, sem bloqueadores.
- UC-002: extração normalizada de produtos, serviços e transportes somente nos grupos operacionais autorizados.
- Homologação real do UC-002: 130 documentos selecionados, 204 registros, 25 componentes, 44 NF-e reconciliadas e nenhum bloqueador de extração.
- Testes: 67 aprovados, incluindo ausência de movimento, migração de schemas, regressões de hash de conteúdo, coerência das saídas, fechamento SQLite e retomada de aprovações preparadas; Ruff, formatação e lock do `uv` aprovados.

## Concluído

- [x] Validação inicial de NF-e/NFC-e.
- [x] Inclusão de NFS-e ABRASF consolidada, prestadas e tomadas.
- [x] Inclusão de CT-e modelo 57 e DACTE.
- [x] Separação por modelo e direção.
- [x] Estados `SEM_DOCUMENTO` e `DOCUMENTO_RESTRITO`.
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
- [x] UC-003C com parser do PGDAS-D, conciliação por estabelecimento e atividade e cobertura parcial sem presunção de não emissão.
- [x] Coordenador `planejar-reforma-tributaria` com retomada por estado, execução automática segura e solicitações em linguagem comum.
- [x] Fila conversacional da carteira com agrupamento, SQLite local, alcance explícito, reaplicação e exportação opcional.
- [x] Processamento incremental de várias competências, com paralelismo limitado, isolamento de falhas e retomada por manifesto local.

A homologação real da política `COMPLEMENTARY` preservou 130 documentos incluídos e `planning_authorized=true`; sem relatório disponível, `reconciliation_ready=false` e 130 ocorrências `XML_WITHOUT_REPORT` permaneceram como avisos. O UC-002 consumiu o schema 1.1.0 sem regressão e manteve 204 registros elegíveis para o UC-003.

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

### 8. UC-003C — conciliação do faturamento no Simples Nacional

O piloto usa a declaração oficial PGDAS-D como autoridade, gera lock por hash e compara a receita do UC-003B por competência, estabelecimento e atividade. Recibo, extrato, DAS e memória do sistema contábil são fontes complementares com papéis distintos.

Na homologação real, comércio e serviços do estabelecimento documental coincidiram integralmente com o PGDAS-D. A declaração também continha outro estabelecimento fora da base fornecida; o resultado correto foi `SIMPLE_REVENUE_PARTIAL_COVERAGE`, com `documentary_scope_reconciled=true`, `group_coverage_complete=false` e `non_issuance_confirmed=false`.

Ainda falta receber e validar a base documental do estabelecimento não coberto. Diferenças por dedução, caixa, competência ou declaração retificadora permanecem na fila do analista e não comprovam não emissão.

### 9. Coordenação orientada ao usuário

O comando `planning-status` lê os artefatos existentes sem refazer etapas concluídas, grava um resumo em `08_STATUS_PLANEJAMENTO/` e informa ações automáticas e entradas humanas por escopo de impacto.

A skill `planejar-reforma-tributaria` usa esse estado como porta de entrada. Ela executa cada ação automática no máximo uma vez por rodada, reavalia o status e interrompe somente diante de entrada indispensável, falha operacional ou funcionalidade ainda não implementada. A resposta padrão evita códigos e gates técnicos e apresenta situação, concluído, achados, necessidade, motivo, continuidade e próximo passo.

O estado também publica um `documentary_summary` agregado e pseudonimizado. O relatório mostra, antes da consolidação, a cobertura documental, entradas e saídas, tipos de documento, populações de produtos/serviços/transportes, valores operacionais, receitas documentais e eventual conciliação com o PGDAS-D. Valores indisponíveis permanecem como não apurados; o resumo não antecipa natureza econômica, receita tributável, crédito ou débito.

### 10. Revisão conversacional da carteira — concluída em 2026-08-31

A skill `revisar-carteira-aquisicoes` recebe uma raiz explicitamente indicada, consolida as filas de aquisições e agrupa ocorrências por assinatura determinística. O analista aprova pela conversa escolhendo natureza, responsável e alcance `ITEM`, `COMPANY` ou `PORTFOLIO`.

As decisões e a auditoria ficam em SQLite dentro da pasta local da carteira. O motor materializa as aprovações no arquivo já consumido pelo UC-003, reprocessa as empresas afetadas e reaplica regras aprovadas a novas ocorrências compatíveis. Regras mais específicas prevalecem sobre regras amplas. O CSV consolidado tornou-se exportação opcional, não autoridade operacional.

Na homologação real pseudonimizada, 70 ocorrências pendentes foram consolidadas em 66 grupos, identificando quatro repetições. A listagem não aprovou nem alterou classificações e gravou somente o estado e o relatório local da carteira.

### 11. Processamento incremental por competência — concluído em 2026-08-31

A skill `processar-periodos-carteira` descobre competências com documentos fiscais, preserva o isolamento por estabelecimento e período e executa até dois períodos simultaneamente por padrão. O manifesto e a configuração de identidade ficam somente em `.reforma-tributaria/`, fora do plugin e do Git.

Cada competência tem hash do conteúdo das entradas, declarações e regras. Períodos só são ignorados quando as saídas também possuem schemas e IDs encadeados coerentes; uma falha fica isolada e não interrompe os demais. A fila central é consolidada uma vez após o lote. A homologação também corrigiu a leitura da competência no PGDAS-D e eliminou duplicação de itens quando o mesmo documento possuía representações XML repetidas.

A revisão posterior endureceu a privacidade de `.reforma-tributaria/`, removeu caminhos absolutos dos resultados públicos, passou a fechar conexões SQLite explicitamente e tornou aprovações recuperáveis por um registro durável `PREPARED` anterior à alteração dos CSVs empresariais.

Na base real, foram descobertas 14 competências fiscais; sete pastas exclusivas do Simples foram corretamente tratadas apenas como fontes de conciliação. Na retomada final, oito períodos foram processados em 85,384 segundos e seis já concluídos foram reaproveitados, sem falhas. A execução seguinte reaproveitou os 14 períodos em 0,310 segundo no motor e 1,622 segundo de ponta a ponta. A fila central resultante contém 240 grupos para revisão humana, sem aprovação automática.

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
- fila central reproduzível, com isolamento de alcance e sem dados reais no Git.
- lote de competências reproduzível, incremental e resiliente a falhas parciais.

## O que não fazer

- não apagar `legacy/mcp/`;
- não copiar XML, PDF, XLSX, CSV real ou credenciais para o repositório;
- não forçar push ou reescrever `main`;
- não tratar validação local como consulta oficial;
- não criar análises operacionais para grupos `SEM_DOCUMENTO`;
- não iniciar novas migrações antes de concluir os itens 1–3.
