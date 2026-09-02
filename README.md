# Planejamento da Reforma Tributária

Plugin local para validação documental e planejamento fiscal rastreável. A validação começa pela base de documentos e só libera a extração de conteúdo nos escopos que possuem evidência suficiente. A aplicação das regras da LC 214 permanece uma etapa posterior, sujeita à revisão do analista.

## Retomar em outra máquina

1. Instale Git, Codex Desktop, Python 3.12 ou superior e `uv`.
2. Clone este repositório para a pasta padrão de plugins do usuário:

   ```text
   git clone https://github.com/Mateusallz1/plugin-reforma.git %USERPROFILE%\plugins\analise-empresarial-reforma-tributaria
   ```

3. Abra uma nova tarefa do Codex com o diretório clonado como contexto e peça:

   ```text
   Leia AGENTS.md e docs/PLANO-DE-CONCLUSAO.md. Retome o trabalho a partir do próximo item pendente, preservando o escopo e as limitações documentadas.
   ```

4. Instale a cópia local pelo marketplace pessoal. Se a marketplace ainda não tiver a entrada local, use o fluxo de criação/atualização do `plugin-creator` para apontá-la ao clone; não crie uma segunda cópia do plugin.
5. Reinicie o Codex Desktop uma vez e abra uma nova tarefa para carregar a versão instalada.

A conversa anterior e a memória da outra máquina não são necessárias: o contrato atual, as decisões e o plano estão versionados neste repositório.

## Arquitetura ativa

- `skills/planejar-reforma-tributaria/`: porta de entrada user-facing; identifica o estágio, executa ações autorizadas e solicita somente a próxima entrada indispensável.
- `skills/processar-periodos-carteira/`: descobre competências fiscais, executa períodos em paralelo limitado e reaproveita resultados sem mudança.
- `skills/validar-base-documental/`: coordenador do UC-001.
- `skills/extrair-conteudo-fiscal/`: coordenador do UC-002; consome apenas documentos autorizados pelo UC-001.
- `skills/revisar-aquisicoes/`: coordenador do UC-003; separa compras e gera fila para decisão do analista.
- `skills/revisar-carteira-aquisicoes/`: consolida pendências repetidas, registra o alcance aprovado e reaplica decisões compatíveis.
- `skills/revisar-receitas/`: segunda frente do UC-003; separa vendas, devoluções, remessas e operações pendentes.
- `skills/revisar-contrapartes/`: apura fornecedores, clientes CNPJ e vendas para CPF com identificadores locais controlados.
- `skills/conciliar-faturamento-simples/`: UC-003C; concilia o UC-003B com o PGDAS-D por estabelecimento e atividade.
- `engine/`: motor Python determinístico compartilhado e gerenciado por `uv`.
- `scripts/invoke-engine.ps1`: bootstrap único do ambiente e do executável usado pelos launchers das skills. Por padrão, o ambiente versionado fica no `LocalApplicationData` do usuário; `FISCAL_INTAKE_ENVIRONMENT` permite apontar outro local controlado.
- `skills/validar-base-documental/references/`: políticas de validade, CT-e, NFS-e, grupos e autorizações por escopo.
- `skills/uv/`: orientação vendorizada da Astral para manutenção do motor.
- Somente `planejar-reforma-tributaria` é roteada implicitamente; skills operacionais e `uv` devem ser invocadas explicitamente.
- `03_SAIDAS/` e demais dados de clientes: ficam fora deste repositório.
- `legacy/mcp/`: bundle Node/MCP arquivado; não faz parte do runtime ativo.

## Escopo documental

O UC-001 cobre NF-e, NFC-e, NFS-e ABRASF e CT-e modelo 57. O resultado separa oito grupos operacionais:

- `NFE_ENTRADAS`, `NFE_SAIDAS`;
- `NFCE_ENTRADAS`, `NFCE_SAIDAS`;
- `NFSE_PRESTADOS`, `NFSE_TOMADOS`;
- `CTE_PRESTADOS`, `CTE_TOMADOS`.

Cada grupo informa se há `COM_DOCUMENTO`, `SEM_DOCUMENTO` ou `DOCUMENTO_RESTRITO`. Só grupos com documento e escopo autorizado devem gerar análise operacional; `SEM_DOCUMENTO` não conclui ausência de operação.

Relatórios CSV/XLSX usam a política `COMPLEMENTARY`: conciliam população, situação e valores, mas não filtram XMLs documentalmente válidos nem incluem notas declaradas sem XML. O campo opcional `report_population_policy` do `escopo.json` assume esse valor; `WHITELIST` permanece reservado para evolução futura.

## Extração de conteúdo

O UC-002 normaliza somente documentos liberados pelo UC-001:

- NF-e/NFC-e: uma linha por produto, com NCM, CFOP, `natOp` do documento, quantidades, valores e campos tributários disponíveis;
- NFS-e: uma linha por serviço, com item da lista, CNAE informado, NBS, valores e ISS disponível;
- CT-e: uma linha por prestação, com CFOP, natureza, modal, produto predominante, componentes e referências.

Os artefatos são gravados em `04_CONTEUDO/`:

- `content-summary.json`: agregados, cobertura, achados e gates, sem descrições comerciais;
- `relatorio-qualidade-conteudo.md`: relatório operacional para o analista;
- `normalized-items.local.jsonl`: conteúdo detalhado local e restrito, que não deve ser copiado para conversa ou Git.

`content_extraction_ready=true` significa que a população foi extraída; eventuais divergências de reconciliação permanecem registradas como observações. Não significa que a classificação da LC 214 esteja concluída. `lcp214_classification_ready` é apenas um indicador de completude dos campos, não autorização ou conclusão jurídica.

Observações de CNAE, NBS, `cClassTrib`, CFOP, descrição, valores ou reconciliação não impedem o início do UC-003. O gate `uc003_analysis_authorized` indica se existe população elegível; `uc003_full_population_ready` indica se nenhum item foi restringido.

Para validar Produto × NCM contra decisão do analista, coloque opcionalmente `00_CONTROLE/catalogo-produtos-ncm.csv` na pasta analisada, com as colunas `codigo_produto`, `ncm_aprovado` e `status`. Somente linhas `APROVADO` podem confirmar divergência. Sem catálogo ou sem correspondência, o motor registra observação e permite avanço provisório; NCM ausente/malformado ou divergente restringe somente o produto afetado.

## Revisão das aquisições

O UC-003 seleciona somente registros de entrada e os separa em `PURCHASE_GOODS`, `PURCHASE_SERVICES` e `PURCHASE_TRANSPORT`. A finalidade econômica não é inferida: o analista pode aprová-la em `00_CONTROLE/classificacao-aquisicoes.csv`; sem decisão, o registro permanece pendente.

Para revisar várias empresas, indique uma raiz de carteira à skill `revisar-carteira-aquisicoes`. Ela agrupa ocorrências com a mesma assinatura, apresenta páginas de até dez grupos e registra decisões em `.reforma-tributaria/revisoes-carteira.sqlite3`. O analista escolhe explicitamente se a aprovação vale para um item, uma empresa ou toda a carteira. Decisões compatíveis são materializadas nos arquivos locais das empresas e reaplicadas quando novas ocorrências surgem no alcance aprovado.

O relatório detalhado permanece local em `.reforma-tributaria/fila-revisao-carteira.local.md`. A exportação CSV é opcional e não é a autoridade operacional.

O par CST/cClassTrib declarado é validado contra snapshot versionado da tabela oficial. Antes de cada execução da skill, a versão publicada deve ser conferida no Portal NF-e. Atualização oficial exige novo snapshot, testes e versão do plugin; uma análise nunca muda silenciosamente de ruleset.

Além do registro no `ruleset-lock`, o motor compara cada snapshot e ruleset com
um hash confiável embarcado. Alterações locais ou arquivos não reconhecidos
interrompem a execução até que a atualização seja revisada e versionada.

As saídas ficam em `05_REVISAO_AQUISICOES/`. O UC-003 inicial não determina direito a crédito e mantém `uc004_planning_authorized=false`.

O resumo também publica `documentary_totals`: cada documento de entrada é
contado uma única vez pelo seu total declarado, com subtotais por tipo e grupo,
devoluções e operações que não representam compra. Documentos mistos ficam em
tratamento pendente; compras sem crédito continuam no total documental.
As operações excluídas também são demonstradas em `excluded_operation_summary`:
o valor total dos documentos aparece uma única vez e o bloco `by_reason` mostra
documentos, itens e valores por motivo CFOP quando o motivo é único. Documentos
com mais de um motivo ficam separados em `mixed_reason_documents`, sem rateio.

## Revisão das receitas

O UC-003B usa o total do documento do UC-001 e os CFOPs dos itens do UC-002. O snapshot oficial CFOP identifica devoluções, retornos, anulações e remessas; o ruleset do analista reconhece CFOPs usuais de venda sem tratá-los como lista exaustiva.

As saídas ficam em `06_REVISAO_RECEITAS/` e separam receita documental bruta, devoluções de venda, operações fora da receita, tratamento pendente e diferenças entre `vNF` e a composição declarada do documento. `net_documentary_revenue_candidate` não representa receita tributável concluída.

O status de planejamento expõe ainda uma comparação informativa entre compras e
vendas do mesmo estabelecimento e competência. A razão usa os candidatos
líquidos, é apresentada com quatro casas quando há denominador positivo e nunca
cria alerta de margem, risco ou omissão.

O UC-002 mantém um snapshot oficial versionado da NCM para verificar existência
e vigência do código informado. O texto oficial é apenas apoio à triagem:
descrição isolada nunca confirma incompatibilidade, benefício ou alíquota. A
fila Produto × NCM e a evidência comercial detalhada permanecem locais.

## Conciliação do Simples Nacional

O UC-003C recebe uma pasta de PDFs do PGDAS-D explicitamente indicada e usa a declaração oficial como autoridade dos valores declarados. A comparação ocorre primeiro por estabelecimento e atividade; um PGDAS-D consolidado com filial não é comparado diretamente a uma base documental apenas da matriz.

Quando a raiz contiver pastas de matriz e filiais na mesma competência, use o
consolidador do Simples. Ele descobre os estabelecimentos já processados,
confirma a mesma empresa pelos identificadores documentais e compara o grupo
com a declaração. Com um único estabelecimento, o fluxo individual permanece
inalterado.

As saídas ficam em `07_CONCILIACAO_SIMPLES/`. Cobertura parcial gera fila para o analista sem presumir não emissão. Recibo e extrato são evidências complementares, DAS não comprova pagamento e memória do sistema contábil não substitui a declaração oficial. O estágio não conclui IBS/CBS e mantém `uc004_planning_authorized=false`.

Se o PGDAS-D indicar regime de apuração `CAIXA`, o resultado apresenta um aviso
não bloqueante e encaminha a análise temporal para o analista.

## Contrapartes e regime

O UC-003D cria uma linha por fornecedor CNPJ, com CRT e situação documental do
Simples, em `05_REVISAO_AQUISICOES/fornecedores-regime.local.jsonl`. Clientes CNPJ
são agrupados em `06_REVISAO_RECEITAS/clientes-cnpj-regime.local.jsonl` e podem
ser resolvidos por um snapshot local JSONL informado ao launcher. Vendas para CPF
são apenas contadas por documento único; nenhum CPF é persistido.

Quando executado diretamente, o UC-003D usa `00_CONTROLE/escopo.json` para
identificar os CNPJs próprios. No processamento de carteira, usa a identidade
validada em `.reforma-tributaria/configuracao-lote.local.json`, sem exigir esse
arquivo em cada competência.

Os resumos públicos mostram somente contagens e valores. Com `-MeetingReport`, o
analista pode gerar localmente `09_APRESENTACAO_CLIENTE/contrapartes-regime.local.md`
com CNPJs e nomes para uma reunião. Esse arquivo é confidencial, opcional e
protegido pelo `.gitignore`.

## Experiência do usuário

Use `planejar-reforma-tributaria` para iniciar ou retomar. O coordenador grava `08_STATUS_PLANEJAMENTO/`, detecta artefatos já existentes e executa as próximas etapas seguras sem exigir que o usuário conheça UCs, launchers, códigos de saída ou gates.

Quando depender de uma decisão humana, a resposta informa em linguagem comum: situação atual, etapas concluídas, achados, entrada necessária, motivo, impacto, o que ainda pode continuar e a próxima ação. A revisão de várias empresas pode continuar pela conversa, sem exigir preenchimento operacional de planilha. As skills operacionais continuam disponíveis para diagnóstico e execução direta.

## Processamento de vários períodos

Use `processar-periodos-carteira` quando a pasta indicada contiver várias competências. O lote descobre as pastas com documentos fiscais, mantém estabelecimento e competência separados e processa até dois períodos simultaneamente por padrão.

As pastas de competência devem estar nomeadas como `MM-AAAA` ou `AAAA-MM`.
Nomes como `01.2026` e `Janeiro-2026` são rejeitados com diagnóstico explícito.
Para o PGDAS-D, o lote procura somente em `SN\<nome-da-pasta>` ou
`SN\<competência AAAA-MM>` dentro da raiz indicada.

O estado fica localmente em `.reforma-tributaria/`, protegido pelo `.gitignore`. Um manifesto registra hashes das entradas e regras usadas em cada competência: períodos só são reaproveitados quando o conteúdo não mudou e os artefatos possuem schemas e IDs coerentes. Conteúdo alterado, saída corrompida ou `force` explícito provoca reprocessamento; uma falha continua isolada dos demais períodos. Pastas que contêm apenas declarações do Simples são fontes de conciliação, não competências fiscais independentes. Ao final, a fila central de revisão é atualizada uma única vez.

Quando houver dois ou mais estabelecimentos processados na mesma competência e
uma única pasta PGDAS-D correspondente, o lote também grava a conciliação
consolidada em `.reforma-tributaria/conciliacoes-simples-grupo/<competência>/`.
Essa saída é derivada da raiz indicada e confirma a cobertura pelos documentos e
pelos estabelecimentos declarados, sem exigir manifesto manual.

## Verificação local

```text
uv run --project engine --group dev pytest engine/tests -q
uv run --project engine --group dev ruff check engine
uv lock --project engine --check
```

O launcher da validação é Windows/PowerShell. Node não é requisito do runtime ativo; só aparece no arquivo legado arquivado.

## Dados reais

Nunca faça commit de bases fiscais reais. Para testar, indique explicitamente uma pasta local do cliente. Os artefatos são gravados na própria pasta analisada, em `03_SAIDAS/` até `08_STATUS_PLANEJAMENTO/`. O `.gitignore` protege essas pastas e qualquer arquivo `*.local.jsonl` como defesa adicional, mas a política principal continua sendo manter dados de clientes fora do repositório.

## Atualizações do plugin

Após alterar o código ou as skills:

1. rode os testes e validadores;
2. atualize o cachebuster pelo `plugin-creator`;
3. reinstale pelo marketplace pessoal;
4. reinicie o Desktop quando necessário;
5. abra uma nova tarefa;
6. faça commit e push somente após revisão.

Veja o plano em [docs/PLANO-DE-CONCLUSAO.md](docs/PLANO-DE-CONCLUSAO.md), a decisão sobre o MCP em [docs/adr/0001-retirar-mcp-do-runtime-ativo.md](docs/adr/0001-retirar-mcp-do-runtime-ativo.md), a revisão conversacional em [docs/adr/0002-revisao-conversacional-da-carteira.md](docs/adr/0002-revisao-conversacional-da-carteira.md) e o lote incremental em [docs/adr/0003-processamento-incremental-por-competencia.md](docs/adr/0003-processamento-incremental-por-competencia.md).
