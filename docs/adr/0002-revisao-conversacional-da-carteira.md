# ADR 0002 — Revisão conversacional da carteira

## Status

Aceita em 2026-08-31.

## Contexto

A fila por empresa exigia repetir classificações equivalentes e usar planilhas como etapa operacional. Em uma carteira com dezenas de empresas, esse modelo não evitava retrabalho do analista.

## Decisão

Manter o runtime em Python e skills, sem reativar MCP ou criar aplicação externa. Uma skill de carteira chama comandos determinísticos do motor para:

- localizar apenas empresas dentro da raiz explicitamente indicada;
- agrupar aquisições por assinatura estável;
- registrar aprovações em SQLite local;
- persistir uma intenção `PREPARED` antes de alterar arquivos empresariais, permitindo retomada idempotente após falha;
- aplicar decisões somente no alcance `ITEM`, `COMPANY` ou `PORTFOLIO` confirmado pelo analista;
- materializar decisões no CSV já consumido pelo UC-003;
- reprocessar as empresas afetadas;
- exportar CSV somente quando solicitado.

Regras mais específicas prevalecem sobre as amplas: `ITEM`, depois `COMPANY`, depois `PORTFOLIO`. Uma aprovação operacional não conclui direito a crédito ou conformidade tributária.

## Consequências

- O analista pode revisar grupos pela conversa e evitar decisões repetidas.
- A base e os detalhes comerciais permanecem na pasta local da carteira.
- A pasta `.reforma-tributaria/` e seus bancos, relatórios e configurações são ignorados pelo Git como defesa em profundidade.
- O fluxo continua funcional sem Node, servidor MCP ou interface web.
- A experiência visual é limitada a páginas textuais e relatório local.
- Uma interface futura poderá consumir o mesmo motor e a mesma base sem alterar a autoridade das regras.
