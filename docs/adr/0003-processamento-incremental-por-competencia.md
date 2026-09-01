# ADR 0003 — Processamento incremental por competência

## Status

Aceita em 2026-08-31.

## Contexto

Uma carteira pode conter vários estabelecimentos e competências. Executar manualmente um mês por vez repete descoberta, preparação e consolidação, mas misturar documentos de meses diferentes comprometeria rastreabilidade, conciliação e retomada.

## Decisão

O usuário informa uma raiz explícita. O lote descobre somente pastas com XML fiscal e trata as pastas de PGDAS-D como fontes declarativas da respectiva competência, não como períodos independentes.

A competência continua sendo a unidade das regras e dos artefatos. O lote é apenas a unidade de execução: usa concorrência limitada, identidade mantida localmente, isolamento de falhas e um manifesto com impressão digital das entradas e dos rulesets. Uma competência sem mudança é reaproveitada; uma competência alterada ou explicitamente forçada é reprocessada.

Ao terminar, a fila central de aquisições é consolidada uma única vez para toda a raiz indicada. Nenhuma classificação é aprovada automaticamente.

## Consequências

- o processamento de várias competências reduz o tempo operacional sem misturar períodos;
- falhas parciais podem ser corrigidas e retomadas sem refazer resultados válidos;
- mudanças em documentos, PGDAS-D ou regras invalidam somente as competências afetadas;
- CNPJ e demais identificadores usados para associar pastas permanecem em configuração local fora do Git;
- a revisão humana continua centralizada e separada da execução documental.
