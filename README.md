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

- `skills/validar-base-documental/`: coordenador do UC-001.
- `skills/extrair-conteudo-fiscal/`: coordenador do UC-002; consome apenas documentos autorizados pelo UC-001.
- `skills/revisar-aquisicoes/`: coordenador do UC-003; separa compras e gera fila para decisão do analista.
- `skills/revisar-receitas/`: segunda frente do UC-003; separa vendas, devoluções, remessas e operações pendentes.
- `skills/validar-base-documental/scripts/motor-planejamento/`: motor Python determinístico gerenciado por `uv`.
- `skills/validar-base-documental/references/`: políticas de validade, CT-e, NFS-e, grupos e autorizações por escopo.
- `skills/uv/`: orientação vendorizada da Astral para manutenção do motor.
- `03_SAIDAS/` e demais dados de clientes: ficam fora deste repositório.
- `legacy/mcp/`: bundle Node/MCP arquivado; não faz parte do runtime ativo.

## Escopo documental

O UC-001 cobre NF-e, NFC-e, NFS-e ABRASF e CT-e modelo 57. O resultado separa oito grupos operacionais:

- `NFE_ENTRADAS`, `NFE_SAIDAS`;
- `NFCE_ENTRADAS`, `NFCE_SAIDAS`;
- `NFSE_PRESTADOS`, `NFSE_TOMADOS`;
- `CTE_PRESTADOS`, `CTE_TOMADOS`.

Cada grupo informa se há `COM_MOVIMENTACAO`, `SEM_MOVIMENTACAO` ou `MOVIMENTACAO_RESTRITA`. Só grupos com movimentação e escopo autorizado devem gerar análise operacional.

Relatórios CSV/XLSX usam a política `COMPLEMENTARY`: conciliam população, situação e valores, mas não filtram XMLs documentalmente válidos nem incluem notas declaradas sem XML. O campo opcional `report_population_policy` do `escopo.json` assume esse valor; `WHITELIST` permanece reservado para evolução futura.

## Extração de conteúdo

O UC-002 normaliza somente documentos liberados pelo UC-001:

- NF-e/NFC-e: uma linha por produto, com NCM, CFOP, quantidades, valores e campos tributários disponíveis;
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

O par CST/cClassTrib declarado é validado contra snapshot versionado da tabela oficial. Antes de cada execução da skill, a versão publicada deve ser conferida no Portal NF-e. Atualização oficial exige novo snapshot, testes e versão do plugin; uma análise nunca muda silenciosamente de ruleset.

As saídas ficam em `05_REVISAO_AQUISICOES/`. O UC-003 inicial não determina direito a crédito e mantém `uc004_planning_authorized=false`.

## Revisão das receitas

O UC-003B usa o total do documento do UC-001 e os CFOPs dos itens do UC-002. O snapshot oficial CFOP identifica devoluções, retornos, anulações e remessas; o ruleset do analista reconhece CFOPs usuais de venda sem tratá-los como lista exaustiva.

As saídas ficam em `06_REVISAO_RECEITAS/` e separam receita documental bruta, devoluções de venda, operações fora da receita, tratamento pendente e diferenças entre `vNF` e soma de `vProd`. `net_documentary_revenue_candidate` não representa receita tributável concluída.

## Verificação local

```text
uv run --project skills/validar-base-documental/scripts/motor-planejamento --group dev pytest skills/validar-base-documental/scripts/motor-planejamento/tests -q
uv run --project skills/validar-base-documental/scripts/motor-planejamento --group dev ruff check skills/validar-base-documental/scripts/motor-planejamento
uv lock --project skills/validar-base-documental/scripts/motor-planejamento --check
```

O launcher da validação é Windows/PowerShell. Node não é requisito do runtime ativo; só aparece no arquivo legado arquivado.

## Dados reais

Nunca faça commit de bases fiscais reais. Para testar, indique explicitamente uma pasta local do cliente. Os artefatos são gravados na própria pasta analisada, em `03_SAIDAS/` e `04_CONTEUDO/`.

## Atualizações do plugin

Após alterar o código ou as skills:

1. rode os testes e validadores;
2. atualize o cachebuster pelo `plugin-creator`;
3. reinstale pelo marketplace pessoal;
4. reinicie o Desktop quando necessário;
5. abra uma nova tarefa;
6. faça commit e push somente após revisão.

Veja o plano em [docs/PLANO-DE-CONCLUSAO.md](docs/PLANO-DE-CONCLUSAO.md) e a decisão sobre o MCP em [docs/adr/0001-retirar-mcp-do-runtime-ativo.md](docs/adr/0001-retirar-mcp-do-runtime-ativo.md).
