# Contrato do relatório de documentos

Use CSV UTF-8 ou a primeira planilha visível de um XLSX. A primeira linha contém os cabeçalhos:

| Campo | Obrigatório | Regra |
|---|---:|---|
| `document_type` | sim | `NFE`, `NFCE` ou `CTE`; NFS-e permanece coberta pelos PDFs municipais nesta versão |
| `access_key` | sim | chave numérica de 44 dígitos; usada somente na conciliação local |
| `issue_date` | sim | data ISO `AAAA-MM-DD` |
| `declared_status` | sim | `AUTHORIZED`, `CANCELLED` ou `UNKNOWN` |
| `gross_amount` | sim | decimal não negativo |
| `source_type` | sim | `AUTHORITY_REPORT`, `ERP_REPORT`, `ACCOUNTING_REPORT` ou `USER_DECLARED` |
| `source_name` | sim | descrição não sensível da origem |
| `generated_at` | sim | data ou data/hora ISO |

O resultado exporta apenas referências pseudonimizadas. A chave completa não deve aparecer em relatórios finais.

## Política da população

O UC-001 usa `report_population_policy=COMPLEMENTARY`:

- XML documentalmente válido continua incluído mesmo ausente do relatório;
- nota declarada sem XML gera `DECLARED_WITHOUT_XML`, mas não entra na população quantitativa;
- divergência de situação ou valor gera aviso;
- valores do XML e do relatório não são somados entre si.

O modo `WHITELIST` não está implementado. Caso seja necessário no futuro, deverá possuir contrato, gates e testes próprios antes de ser aceito no `escopo.json`.
