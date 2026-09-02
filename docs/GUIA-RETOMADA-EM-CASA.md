# Guia de retomada em outra máquina

Este arquivo é o ponto de partida para continuar o plugin em casa ou em outra
máquina. A fonte de verdade do código é a branch `main` do repositório
`https://github.com/Mateusallz1/plugin-reforma.git`. A versão funcional deve ser
conferida em `.codex-plugin/plugin.json`; o sufixo `+codex.*` é somente o
cachebuster da instalação.

## Pré-requisitos

- Windows com PowerShell;
- Codex Desktop ou Codex CLI;
- `uv` disponível no `PATH` para preparar o runtime Python na primeira execução;
- Git, quando a instalação for mantida por clone;
- nenhuma dependência Node ou servidor MCP: o MCP legado não faz parte do runtime
  atual.

Após instalar ou reinstalar, abra uma nova task/conversa para o Codex carregar as
skills e o novo launcher.

## Atualizar o código

Em um clone existente, use:

```powershell
git pull --ff-only origin main
```

Não copie dados de clientes para o clone. XML, PDF, CSV, JSONL local, SQLite,
relatórios de reunião e saídas das competências devem permanecer fora do
repositório ou protegidos pelo `.gitignore`.

## Convenção da carteira

Para várias competências, indique somente a raiz que contém os estabelecimentos:

```text
<raiz>/MATRIZ/01-2026/
<raiz>/MATRIZ/02-2026/
<raiz>/FILIAL/01-2026/
<raiz>/FILIAL/02-2026/
<raiz>/SN/01-2026/       # fonte PGDAS-D, não competência fiscal independente
```

Os nomes das competências devem ser `MM-AAAA` ou `AAAA-MM`. Formatos como
`01.2026` e `Janeiro-2026` não são reconhecidos.

## Fluxo de execução

1. **UC-001 — base documental**: valida NF-e, NFC-e, NFS-e e CT-e e autoriza
   os escopos documentais.
2. **UC-002 — conteúdo**: extrai produtos, serviços e transportes; problema
   confirmado Produto × NCM restringe somente o item.
3. **UC-003 — aquisições e receitas**: separa compras, remessas, devoluções,
   serviços e transportes; a natureza econômica depende do analista.
4. **UC-003C — PGDAS-D**: concilia receita por estabelecimento e, quando a
   carteira comprova matriz e filial pelo mesmo CNPJ-base, consolida o grupo.
5. **UC-003D — contrapartes**: apura fornecedores, clientes CNPJ e vendas para
   CPF. CRT válido é evidência documental; CRT ausente ou inválido resulta em
   `REGIME_INDETERMINADO`.
6. **UC-004 — simulação**: calcula exposição comercial e crédito estimado. É
   `SIMULATION_ONLY`; não autoriza crédito legal nem altera o regime da empresa.

Para processar uma carteira:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  skills/processar-periodos-carteira/scripts/run-portfolio-batch.ps1 `
  -Action Plan -PortfolioFolder <raiz>

powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  skills/processar-periodos-carteira/scripts/run-portfolio-batch.ps1 `
  -Action Process -PortfolioFolder <raiz>
```

Para a simulação consolidada:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
  skills/simular-credito-ibs-cbs/scripts/run-credit-planning.ps1 `
  -Folder <raiz>
```

Acrescente `-MeetingReport` somente quando o analista solicitar o relatório
identificado local.

## Entradas adicionais

Para resolver clientes ou fornecedores que não tenham regime documental
conclusivo, forneça um snapshot local JSONL ao lote:

```powershell
...run-portfolio-batch.ps1 -Action Process -PortfolioFolder <raiz> `
  -SimplesRegistry <arquivo-jsonl>
```

O formato está em
`skills/revisar-contrapartes/references/simples-registry.schema.md`. O arquivo
deve permanecer na pasta do cliente e nunca entrar no Git.

## Saídas e leitura

Cada competência grava resultados separados em `03_SAIDAS/` até
`08_STATUS_PLANEJAMENTO/`. O UC-004 grava:

```text
10_PLANEJAMENTO_CREDITOS/
├── credit-planning-summary.json
├── portfolio-credit-planning-summary.json  # quando a entrada é uma carteira
├── credit-planning.local.jsonl
└── credit-planning.local.md                # somente com -MeetingReport
```

O resumo público contém somente totais, percentuais, cenários e gates. Os
artefatos locais podem conter `NOME EMPRESA + CNPJ`, produtos e valores por
fornecedor; eles são confidenciais.

## Regras do UC-004

- A receita-base é a soma da receita PGDAS-D conciliada no período selecionado.
- A linha de corte é `20%` dessa receita.
- Clientes de regime normal compõem a população que exige crédito integral.
- Simples, MEI, nanoempreendedor, PF, condomínios, órgãos públicos e governo
  ficam fora dessa população quando a classificação estiver evidenciada.
- Se PGDAS-D for maior que XML, a diferença recebe o nome técnico
  `RECEITA_SEM_NOTA_FISCAL`: é tributada no Simples como receita declarada e
  não recebe benefício fiscal. A indicação de PF é apenas uma premissa de
  segmentação, não uma identificação comprovada.
- Se XML for maior que PGDAS-D, a recomendação fica
  `PENDING_REVENUE_DIVERGENCE`.
- O cenário atual estima 9% para fornecedor normal confirmado, 1% para Simples
  e 0% para MEI, nanoempreendedor, PF e regime indeterminado. Todas as taxas
  são previsões editáveis, não créditos legais.

## Diagnóstico real de referência

Na carteira MR Extintores usada nos testes:

- 14 competências foram processadas;
- matriz e filial foram reconhecidas como a mesma empresa pelo CNPJ-base;
- a cobertura de grupo do PGDAS-D ficou completa;
- diferenças documentais ainda exigem revisão em algumas competências;
- o UC-004 permanece `PENDING_CUSTOMER_REGIME_LOOKUP` sem snapshot de regime
  dos clientes;
- crédito estimado igual a `0.00` pode refletir natureza/evidência pendente ou
  regime não confirmado; não significa crédito legal inexistente.

## Como retomar uma pendência

- `PENDING_GROUP_CONSOLIDATION`: conferir as pastas de matriz/filial e a
  configuração local do grupo.
- `PENDING_CUSTOMER_REGIME_LOOKUP`: executar o `simples-check`/snapshot local
  e repetir a simulação.
- `PENDING_REVENUE_DIVERGENCE`: revisar a diferença entre PGDAS-D e XML com o
  analista.
- `PENDING_OPERATIONAL_EVIDENCE`: aprovar a natureza da aquisição e confirmar
  a evidência CST/cClassTrib.
- `REGIME_INDETERMINADO`: preservar a classificação, registrar o motivo e não
  atribuir automaticamente Simples, normal ou pessoa física.

O resultado é sempre uma ferramenta de apoio. A aprovação do analista continua
sendo necessária para a natureza econômica, a política comercial e qualquer
conclusão tributária.
