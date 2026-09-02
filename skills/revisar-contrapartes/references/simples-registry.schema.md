# Snapshot local de situação do Simples

O arquivo opcional informado em `-SimplesRegistry` deve ser JSONL UTF-8, com
uma linha por situação temporal de CNPJ:

```json
{"cnpj":"00000000000100","status":"OPTANTE_SIMPLES","effective_from":"2026-01-01","effective_to":"9999-12-31","source":"RFB_SIMPLES_SNAPSHOT","verified_at":"2026-09-02"}
```

Campos obrigatórios:

- `cnpj`: CNPJ completo, com ou sem formatação;
- `status`: `OPTANTE_SIMPLES`, `NAO_OPTANTE_SIMPLES` ou `INDETERMINADO`;
- `effective_from` e `effective_to`: intervalo ISO `AAAA-MM-DD`;
- `source`: identificação da fonte oficial ou do snapshot aprovado;
- `verified_at`: data em que a fonte foi conferida.

O motor considera a interseção do intervalo com a competência analisada. Mais
de um status para o mesmo CNPJ na competência produz
`DIVERGENTE_NO_PERIODO`; o motor não escolhe um registro.

A opção pelo Simples é consultada por CNPJ básico na fonte oficial, mas o
resultado local continua sendo materializado por CNPJ completo para manter a
lista de contrapartes do estabelecimento. O arquivo contém dados sensíveis e
deve permanecer na pasta do cliente.
