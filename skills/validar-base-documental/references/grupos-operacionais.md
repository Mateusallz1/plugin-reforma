# Grupos operacionais para análise futura

O UC-001 preserva `document_type` e `direction` e acrescenta `analysis_group` a cada registro. Use estes códigos estáveis para alimentar as próximas etapas do planejamento:

| Grupo | Modelo | Papel da empresa |
|---|---|---|
| `NFE_ENTRADAS` | NF-e | destinatária |
| `NFE_SAIDAS` | NF-e | emitente |
| `NFCE_ENTRADAS` | NFC-e | destinatária |
| `NFCE_SAIDAS` | NFC-e | emitente |
| `NFSE_PRESTADOS` | NFS-e | prestadora |
| `NFSE_TOMADOS` | NFS-e | tomadora |
| `CTE_PRESTADOS` | CT-e | emitente |
| `CTE_TOMADOS` | CT-e | tomadora |

`documents.analysis_groups` sempre apresenta os oito grupos para manter o esquema estável. Cada grupo informa `detected_count`, documentos incluídos em `count`, `gross_amount`, `analysis_scope`, autorização e estado de movimentação.

- `COM_MOVIMENTACAO`: existe documento incluído e o escopo está autorizado; `operational_analysis_required=true`;
- `SEM_MOVIMENTACAO`: nenhuma ocorrência em escopo foi detectada; não crie análise operacional;
- `MOVIMENTACAO_RESTRITA`: há ocorrência, mas o escopo não está autorizado ou nenhum documento ficou elegível; não crie análise até resolver a restrição.

O relatório mostra tabelas operacionais somente para grupos com ocorrência e lista separadamente os grupos sem movimentação. Não gere seções, cálculos ou diagnósticos vazios para grupos `SEM_MOVIMENTACAO`.

Não traduza automaticamente NF-e/NFC-e como “mercadorias”: esta camada separa modelos documentais e papéis operacionais, não conclui a natureza tributária do item. Documentos com direção `BOTH` ou `NAO_VERIFICAVEL` recebem `NAO_CLASSIFICADO` e exigem tratamento posterior explícito.
