# Autorizações por escopo documental

O UC-001 avalia separadamente os escopos `NFE_NFCE`, `NFSE` e `CTE`. Um problema em uma família não invalida automaticamente as famílias prontas.

## Estados por escopo

- `READY`: há documentos incluídos e nenhum bloqueador daquele escopo;
- `BLOCKED`: o escopo foi declarado ou detectado, mas possui bloqueador ou nenhum documento elegível;
- `NOT_DETECTED`: o escopo não foi declarado nem encontrado.

Cada registro expõe `analysis_scope` e `authorized_for_planning`. Somente registros incluídos pertencentes a um escopo `READY` podem alimentar etapas posteriores.

Um escopo `READY` não implica criar todas as análises operacionais possíveis. Consulte `documents.analysis_groups`: crie somente as análises com `operational_analysis_required=true`; grupos `SEM_DOCUMENTO` permanecem registrados, mas não produzem análise vazia.

## Gates globais

- `planning_authorized`: ao menos um escopo está `READY`;
- `scope_analysis_ready`: existe população autorizada para análise;
- `full_documentary_coverage_ready`: todos os escopos declarados ou detectados estão prontos e não há restrição desconhecida;
- `authorized_scopes`: escopos liberados;
- `restricted_scopes`: escopos detectados ou declarados que permanecem bloqueados.

Use `DOCUMENT_BASE_READY_WITH_SCOPE_LIMITATIONS` quando houver ao menos um escopo autorizado e outro restrito. Nesse estado, permita análise somente dos escopos autorizados e proíba conclusões de cobertura integral.

Use `DOCUMENT_BASE_BLOCKED` apenas quando nenhum escopo puder prosseguir. Arquivo desconhecido ou família ainda não suportada restringe cobertura integral, mas não elimina populações independentes já validadas.
