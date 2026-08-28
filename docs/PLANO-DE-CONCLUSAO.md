# Plano de conclusão da etapa de ajustes

## Baseline atual

- Plugin: `0.22.0+codex.20260828190704`.
- Branch: `main`.
- Último commit publicado: `2b45532` (`refactor: retire legacy MCP runtime`).
- Runtime ativo: Python/`uv`, sem servidor MCP no manifesto.
- Skills ativas: `uv` e `validar-base-documental`.
- UC-001: NF-e, NFC-e, NFS-e ABRASF e CT-e modelo 57.
- Esquema de saída: `1.7.0`, com autorização por escopo e oito grupos operacionais.
- Homologação real: 130 documentos incluídos, três escopos `READY`, sem bloqueadores.
- Testes: 14 aprovados, Ruff e lock do `uv` aprovados.

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

## Próximos ajustes, em ordem

### 1. Tornar `uv` explicit-only

Criar ou atualizar `skills/uv/agents/openai.yaml` com `allow_implicit_invocation: false`. Manter o texto vendorizado da Astral sem alterações. A execução do motor continua usando `uv` internamente; somente o roteamento automático da skill deixa de ocorrer.

Saída esperada: análises normais não carregam a skill `uv`; manutenção explícita do motor continua possível.

### 2. Reescrever o fast path positivamente

Substituir a enumeração de proibições por um contrato curto:

1. execute o launcher uma vez;
2. leia os dois artefatos em `03_SAIDAS`;
3. respeite `authorized_scopes`, `restricted_scopes` e `operational_analysis_required`;
4. só entre em diagnóstico se o launcher falhar ou os artefatos estiverem ausentes.

Não alterar o motor, os gates, a privacidade ou os códigos de saída.

### 3. Validar a retomada em máquina limpa

Clonar o repositório em outra conta Windows, instalar o plugin local, reiniciar o Desktop e executar uma base sintética. Confirmar que `AGENTS.md`, `README.md` e as referências direcionam o trabalho sem depender da conversa anterior.

### 4. Homologar o modelo de relatório do analista

Quando o modelo final do cliente estiver disponível, registrá-lo como asset/template versionado e separar claramente:

- dados observados pelo motor;
- regras fornecidas pelo analista;
- hipóteses e premissas;
- conclusão sujeita à aprovação fiscal.

Não colocar o modelo homologado dentro do motor de validação documental.

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
