# ADR 0001 - Retirar o MCP do runtime ativo

- Status: aceita
- Data: 2026-08-28
- Escopo: plugin `analise-empresarial-reforma-tributaria`

## Contexto

O plugin contém dois fluxos independentes:

1. o UC-001 em Python, gerenciado por `uv`, com validação determinística e saídas em arquivo;
2. um bundle Node legado exposto por MCP, com resultados mantidos em memória e paginação por `analysis_id`.

O fluxo Python passou a ser a autoridade da validação documental. Ele produz `validation-result.json` e `relatorio-prontidao-documental.md`, o que elimina a necessidade de manter respostas extensas em memória apenas para paginação.

Os motores têm coberturas e schemas diferentes. Mantê-los ativos como autoridades paralelas aumenta o risco de resultados contraditórios e duplica o custo de manutenção.

O bundle `server.mjs` é o único artefato disponível do motor Node. Não há código-fonte JS/TS reconstruível no plugin, portanto ele não pode ser apagado durante a simplificação.

## Decisão

- O transporte MCP será retirado do runtime ativo do plugin.
- O motor Python do UC-001 será a autoridade da validação documental.
- Saídas duráveis serão gravadas em arquivos locais; não será mantido `analysis_id` paginado no fluxo novo.
- `server.mjs`, `.mcp.json`, o launcher e a skill legada serão preservados em arquivo versionado antes de saírem das rotas ativas.
- Capacidades exclusivas do Node não serão portadas implicitamente. Cada migração exigirá necessidade real, contrato próprio e testes.
- Enriquecimento de regime por `localhost:8877` poderá retornar futuramente como opção explícita do CLI, sem reintroduzir o MCP como transporte.

Esta decisão não autoriza apagar o legado. A retirada efetiva do manifesto e de `skills/` será uma mudança posterior, revisável e coberta por Git.

## Consequências positivas

- uma única autoridade para validação documental;
- menor ambiguidade de roteamento;
- remoção de Node como requisito do runtime ativo;
- eliminação de paginação e estado em memória para resultados que já possuem artefatos locais;
- evolução do core baseada em contratos e testes do motor Python.

## Consequências e perdas aceitas

Enquanto não forem migradas, o fluxo ativo deixará de oferecer as capacidades exclusivas listadas em [inventario-capacidades-mcp-legado.md](../inventario-capacidades-mcp-legado.md), incluindo ZIP, NFS-e Nacional, DPS e enriquecimento local de regime.

Os perfis analíticos do bundle Node não serão tratados como equivalentes aos futuros módulos do core. Eles permanecem evidência histórica e fonte de requisitos, não implementação oficial.

## Plano de transição

1. Manter o baseline Git e os hashes dos artefatos legados.
2. Arquivar os arquivos e referências do MCP sem alterar `server.mjs`.
3. Remover `mcpServers` do manifesto ativo.
4. Retirar a skill legada da descoberta automática.
5. Validar o plugin sem Node/MCP e reinstalá-lo pelo marketplace pessoal.
6. Migrar capacidades exclusivas apenas quando entrarem no escopo do core.

## Critérios de conclusão

- o plugin instalado não registra servidor MCP;
- o fast path executa apenas o launcher Python e lê os dois artefatos fixos;
- o bundle legado continua recuperável e com checksum válido;
- testes, validação estrutural e base real permanecem aprovados;
- a documentação ativa não orienta o usuário a utilizar o MCP.

## Estado de implementação

Em 2026-08-28, o legado foi movido para `legacy/mcp/`, a skill antiga saiu de `skills/` e `mcpServers` foi removido do manifesto ativo. Os hashes foram preservados e a cópia instalada `0.22.0` passou na validação estrutural e no UC-001 real. A transição está pronta para revisão e commit.
