# Contexto operacional do plugin

## Autoridade atual

- O fluxo ativo é a skill `validar-base-documental` com motor Python gerenciado por `uv`.
- A validação documental grava `validation-result.json` e `relatorio-prontidao-documental.md` na pasta do cliente.
- O MCP não faz parte do runtime ativo. O legado está preservado em `legacy/mcp/` apenas para consulta e migração futura.
- Não executar, editar ou reativar arquivos de `legacy/mcp/` durante uma análise normal.

## Escopo homologado

- NF-e e NFC-e com direção `ENTRADA`/`SAIDA`.
- NFS-e ABRASF com direção `NFSE_PRESTADOS`/`NFSE_TOMADOS`.
- CT-e modelo 57, leiaute 4.00, com direção `CTE_PRESTADOS`/`CTE_TOMADOS`.
- PDFs auxiliares: DANFE, DACTE, impressões de NFS-e e livros fiscais.
- Autorização por escopo: uma família restrita não invalida famílias independentes prontas.
- Grupos sem ocorrência ficam `SEM_MOVIMENTACAO` e não geram análise operacional.

## Privacidade e evidência

- Nunca copie XML, PDF, XLSX, CSV real, CNPJ, CPF, chave fiscal ou credencial para este repositório.
- Dados de clientes permanecem fora do plugin e fora do Git.
- O JSON técnico e a conversa permanecem pseudonimizados; somente o relatório local pode identificar a empresa-alvo.
- `VALID_DOCUMENTARY` é coerência documental local, não consulta atual à autoridade, validação de assinatura ou parecer tributário.

## Como verificar alterações

Execute os comandos Python por `uv`, nunca por `pip` ou por um ambiente manual:

```text
uv run --project skills/validar-base-documental/scripts/motor-planejamento --group dev pytest skills/validar-base-documental/scripts/motor-planejamento/tests -q
uv run --project skills/validar-base-documental/scripts/motor-planejamento --group dev ruff check skills/validar-base-documental/scripts/motor-planejamento
uv run --project skills/validar-base-documental/scripts/motor-planejamento --group dev ruff format --check skills/validar-base-documental/scripts/motor-planejamento
uv lock --project skills/validar-base-documental/scripts/motor-planejamento --check
```

Antes de empacotar, valide as skills e o plugin com os validadores oficiais. Depois reinstale pelo marketplace pessoal e abra uma nova tarefa do Codex.

## Ordem de trabalho pendente

Leia [docs/PLANO-DE-CONCLUSAO.md](docs/PLANO-DE-CONCLUSAO.md) antes de iniciar uma nova alteração. O próximo passo é validar a retomada em uma máquina Windows limpa; depois, homologar o modelo final de relatório do analista.

## Git e mudanças externas

- Branch principal: `main`.
- Repositório remoto: `https://github.com/Mateusallz1/plugin-reforma.git`.
- Não fazer force push, apagar histórico, criar remoto ou alterar dados de cliente sem autorização explícita.
- Staging deve usar caminhos explícitos; commits devem ser pequenos e descritivos.
