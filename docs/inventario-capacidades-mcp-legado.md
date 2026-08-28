# Inventário de capacidades do MCP legado

## Evidência preservada

- Artefato: `legacy/mcp/server.mjs`
- SHA-256: `2A7397963B293E0326FFCCF842D048EC2C09DB87078445784E04DD9C9D78EF0A`
- Servidor MCP: `0.9.0`
- Schema de análise empresarial: `2.9.0`
- Ferramentas: `analyze_company_folder` e `get_company_analysis_page`

Este documento registra capacidades observadas no bundle para evitar perda silenciosa durante a retirada do MCP. Não transforma o bundle em autoridade atual.

## Matriz de capacidades

| Capacidade | Node/MCP legado | Python UC-001 | Destino recomendado |
|---|---|---|---|
| Leitura recursiva de XML | sim | sim | manter no Python |
| Leitura de ZIP | sim | não | backlog; migrar somente com caso real e limites de segurança |
| NF-e/NFC-e | sim | sim | Python é a autoridade |
| NFS-e ABRASF | sim | sim | Python é a autoridade na cobertura homologada |
| NFS-e Nacional | sim | não | backlog separado; não aproximar ao parser ABRASF |
| DPS | reconhece e preserva limitações | não | backlog; manter DPS fora da população emitida |
| CT-e modelo 57 | não comprovado no bundle | sim | manter no Python |
| DANFE, DACTE e PDFs fiscais | não comprovado no bundle | sim | manter no Python |
| Autorização por escopo documental | não equivalente | sim | manter no Python |
| Grupos operacionais e sem movimentação | não equivalente | sim | manter no Python |
| Relatórios JSON e Markdown em arquivo | não; resposta MCP paginada | sim | manter no Python |
| `analysis_id` e paginação | sim | desnecessário | não migrar |
| Enriquecimento `LOCAL_RFB` em `localhost:8877` | sim | não | possível flag futura do CLI |
| Provedores remotos de regime | sim | não | não migrar sem autorização e contrato de privacidade |
| Perfis de partes e contrapartes | sim | não | fonte de requisitos para o core futuro |
| Perfis de risco, créditos e débitos | sim | não | redesenhar no core; não copiar como caixa-preta |
| Evidências de extinção e Simples | sim | não | backlog condicionado às regras do analista |
| Ledger operacional e reconciliação de receita | sim | parcial/diferente | redesenhar sobre grupos autorizados do Python |
| Minimização de dados e ausência de XML bruto | sim | sim | requisito obrigatório em qualquer migração |

## Capacidades que podem ser abandonadas com o MCP

- transporte stdio MCP;
- armazenamento de até poucas análises em memória;
- `analysis_id` e paginação de seções;
- schemas de ferramentas específicos do MCP;
- dependência de Node no runtime ativo.

## Capacidades que devem permanecer preservadas como requisitos

- ZIP com limites, deduplicação e origem relativa;
- distinção entre NFS-e emitida e DPS;
- NFS-e Nacional;
- consulta local de regime sem envio externo de dados;
- evidência temporal de regime;
- cobertura, limitações e estados conservadores dos perfis fiscais;
- privacidade e pseudonimização.

## Regra de migração

Uma capacidade só entra no motor Python quando houver:

1. caso de uso atual aprovado;
2. amostra sintética e, quando autorizado, homologação real;
3. contrato de entrada e saída;
4. regra de privacidade;
5. testes de regressão;
6. documentação de limitações e autoridade da evidência.
