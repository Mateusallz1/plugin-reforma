# MCP legado arquivado

Este diretório preserva o runtime Node/MCP anterior à consolidação do UC-001 em Python. Seus arquivos não fazem parte das rotas ativas do plugin.

## Estado

- congelado para recuperação e consulta histórica;
- não reconstruível a partir de código-fonte neste repositório;
- não deve ser carregado como skill ou servidor MCP;
- checksums registrados em `../../LEGACY_ARTIFACTS.sha256`;
- decisão arquitetural registrada em `../../docs/adr/0001-retirar-mcp-do-runtime-ativo.md`.

## Conteúdo

- `server.mjs`: bundle Node preservado byte a byte;
- `.mcp.json`: configuração antiga do servidor;
- `scripts/`: launcher Windows antigo;
- `skills/diagnosticar-reforma-tributaria/`: skill e referências da arquitetura anterior;
- `PLANO-DE-IMPLEMENTACAO.md`: plano antigo baseado no MCP.

## Regra de uso

Não edite ou execute estes arquivos como parte do fluxo normal. Consulte-os somente para recuperar requisitos, comparar comportamento histórico ou planejar uma migração explícita para o motor Python.
