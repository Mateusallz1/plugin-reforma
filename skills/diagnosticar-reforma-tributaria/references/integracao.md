# Integração com a pasta empresarial

O plugin usa `analyze_company_folder` para processar localmente os XMLs e ZIPs da pasta indicada pelo usuário. A ferramenta devolve resumo, cobertura e um `analysis_id`; os detalhes são consultados por `get_company_analysis_page` sem retornar XML bruto nem caminhos absolutos.

## Ferramentas MCP

- `analyze_company_folder`: execute uma vez por pasta. `target_taxpayer_ids` é opcional; quando omitido, a ferramenta identifica a empresa predominante por recorrência, cobertura e papéis documentais. Por padrão, use `enrich_tax_regimes=true` e `regime_provider=LOCAL_RFB`; a consulta permanece em `localhost:8877` e não exige consentimento de envio externo.
- `get_company_analysis_page`: além das seções fiscais, consulte `party_relationships`, `sales_party_types`, `regime_evidence`, `document_validity_overrides`, `operational_ledger`, `operational_periods`, `declared_revenue_periods` e `revenue_reconciliation`, com páginas de até 50 itens.

## Descoberta, contrapartes e regime

`target_discovery` agrupa matriz e filiais pelo CNPJ básico e informa candidatos, cobertura e confiança. Recorrência 80/20 seleciona automaticamente a entidade predominante quando a vantagem é conclusiva; empate ou cobertura insuficiente exige escolha do usuário pelo nome encontrado, sem exigir digitação do CNPJ.

CNPJ alfanumérico com validação local `NOT_VERIFIABLE` não participa da descoberta automática nesta versão. Use identificação explícita quando necessário e apresente essa limitação no diagnóstico.

`party_profile` separa fornecedores, compradores, CPF, CNPJ, consumidor não identificado e identificação inválida. Dez notas do mesmo CNPJ geram um relacionamento agregado e uma única candidatura de consulta. CPF é pseudonimizado, nunca é enviado ao provedor e indica pessoa física, não consumidor final por si só. Use `finalConsumerDocuments` somente quando `indFinal` confirmar essa condição.

O enriquecimento é tardio: XMLs são processados, duplicidades removidas, ledger construído e CNPJs agrupados antes da consulta. `LOCAL_RFB` usa automaticamente a base local de `localhost:8877`. `PUBLIC_APIS` e `SIMPLES_CHECK` remoto são alternativas explícitas e exigem autorização porque enviam CNPJs para fora da máquina. `regime_evidence` preserva `OPTANTE`, `NAO_OPTANTE` ou `UNKNOWN`, fonte, período e data da consulta. `SEM_REGISTRO_SIMPLES` com `NAO_OPTANTE` é conclusivo como evidência cadastral, mas nunca cria período `SIMPLES_NACIONAL`. `null`, datas inválidas, período invertido, timeout, rede ou HTTP produzem `UNKNOWN`.

`PUBLIC_APIS` não usa chave. O provedor `SIMPLES_CHECK` assume `http://localhost:8877` no piloto e aceita `SIMPLES_CHECK_BASE_URL` para substituição. `SIMPLES_CHECK_API_KEY` permanece opcional para uma implantação privada futura; nunca grave chaves em prompt, relatório, skill ou arquivo versionado.

Cada item de `tax_regime_periods` usa `taxpayer_id`, `valid_from`, `valid_to` opcional, `regime` (`SIMPLES_NACIONAL`, `REGULAR` ou `OTHER`) e `ibs_cbs_mode` (`WITHIN_SIMPLES`, `REGULAR` ou `UNKNOWN`). Os intervalos são inclusivos e não podem se sobrepor para o mesmo contribuinte. No Simples, não presuma a modalidade: use `UNKNOWN` quando a opção IBS/CBS não estiver comprovada.

`counterparty_tax_regime_periods` usa o mesmo formato para clientes e fornecedores. Pode ser declarado pelo usuário ou enriquecido por fonte pública. O perfil de créditos avalia separadamente o regime da adquirente e o regime do fornecedor; consulta do Simples com forma de recolhimento desconhecida não libera conclusão automática.

## Contexto das aquisições

`acquisition_contexts` vincula contexto empresarial a uma entrada por `document_ref` e `item_number`. O `document_ref` deve ser copiado da seção `documents`; ele é estável para o mesmo conteúdo e não depende do caminho local.

Cada contexto informa:

- `destination`: `RESALE`, `PRODUCTION_INPUT`, `SERVICE_INPUT`, `USE_OR_CONSUMPTION`, `FIXED_ASSET`, `PERSONAL_OR_NON_BUSINESS`, `OTHER` ou `UNKNOWN`;
- `business_activity_link`: `CONFIRMED`, `NOT_CONFIRMED` ou `UNKNOWN`;
- `subsequent_operation_treatment`: `TAXED`, `ZERO_RATE`, `EXEMPT`, `IMMUNE`, `EXPORT`, `NOT_APPLICABLE` ou `UNKNOWN`.

Referência desconhecida, item inexistente ou contexto duplicado é rejeitado. Quando os identificadores ainda não forem conhecidos, execute primeiro sem contextos, consulte `documents` e depois reexecute a pasta com os mesmos parâmetros mais `acquisition_contexts`. Não misture os dois `analysis_id`.

`POTENTIAL_CREDIT_WITH_CONTEXT` exige documento conforme com IBS/CBS, regime regular, destinação empresarial conhecida, vínculo confirmado e operação subsequente `TAXED`. Ele continua sendo indício, não crédito apropriado. `PERSONAL_OR_NON_BUSINESS` ou vínculo `NOT_CONFIRMED` gera `RISK_OF_IMPEDIMENT`. Ativo imobilizado e tratamentos subsequentes especiais permanecem em `REQUIRES_NORMATIVE_VALIDATION` nesta etapa.

## Montantes declarados do Simples

`simples_tax_amounts` registra o IBS e a CBS declarados como devidos por meio do Simples para uma saída/item. Cada entrada usa `document_ref`, `item_number`, `calculation_period`, `ibs_amount`, `cbs_amount` e `source_type` (`DECLARED_SIMPLES_ASSESSMENT`, `DECLARED_ACCOUNTING_ALLOCATION` ou `DECLARED_OTHER`).

O documento deve ser uma saída da empresa no Simples `WITHIN_SIMPLES`, e a competência deve coincidir com a emissão. O resultado mantém `evidenceStatus=USER_DECLARED` e `paymentStatus=NOT_ASSESSED`. `declaredSimplesTaxAmount` não é `documentedTaxValue`, não prova apuração oficial e não pode ser apresentado como crédito apropriado.

Os montantes são indexados por `documentRef:itemNumber` para manter custo linear no volume de itens e entradas declaradas. Falhas objetivas de classificação, vigência ou valor têm precedência sobre o enquadramento no Simples; consulte os achados de risco antes de usar o montante.

Sem montante, permanece `SIMPLES_CUSTOMER_CREDIT_AMOUNT_PENDING`. Com montante positivo, use `SIMPLES_CUSTOMER_CREDIT_AMOUNT_DECLARED`, ainda condicionado à extinção e à idoneidade documental. Valor zero produz ausência de indício e requer confirmação da apuração.

## Evidências de extinção

`debit_extinction_evidence` registra eventos por `document_ref` e `item_number`, com `evidence_ref` pseudonimizado, `event_date`, `modality`, `event_status`, valores de IBS/CBS e `source_type`. As modalidades cobrem compensação, pagamento pelo contribuinte, split payment, recolhimento pelo adquirente e pagamento por responsável.

O usuário declara somente evento pendente ou aplicado. O motor deriva `NOT_ASSESSED`, `PENDING`, `PARTIALLY_EXTINGUISHED`, `EXTINGUISHED`, `REFERENCE_AMOUNT_MISSING` ou `INCONSISTENT`. Consulte `debit_extinctions` para a reconciliação.

`EXTINGUISHED` significa igualdade matemática entre valores aplicados declarados e a referência. Não prova autenticidade, reconhecimento oficial, pagamento real ou crédito apropriado. Eventos com valor superior à referência são `INCONSISTENT`. Data ausente, inválida ou não verificável usa `effectStatus=NOT_DETERMINED`.

## Livro operacional e validade

NF-e/NFC-e usam internamente chave de 44 dígitos com DV e coerência estrutural; duplicidades são eliminadas por chave e fingerprint. A chave não é exportada no JSON, ledger ou MCP. `lifecycleStatus` distingue documento autorizado, cancelado, não confirmado e não verificável. Autorização exige protocolo na hierarquia correta.

Cancelamento confirmado incorporado ao `nfeProc` é reconhecido somente quando pedido e resposta estão na hierarquia e namespace corretos, usam `tpEvento=110111`, a mesma chave e sequência, protocolo numérico e `cStat` homologado (`135` ou `155`). Nesse caso, `CANCELLED` tem precedência e um override `VALID` não reabilita o documento. Pedido sem resposta homologada não comprova cancelamento. A associação automática de evento avulso permanece não homologada.

`operational_ledger` separa comércio, serviços prestados/tomados, compras, devoluções e saídas em revisão. CFOP fora da política validada não é presumido como receita. `excludedAmount` contém documentos sem validade operacional e não deve ser somado a `unclassifiedAmount`. Documentos com CFOPs mistos de devolução permanecem em revisão. Consulte `operational_periods` para totais mensais.

NFS-e reconhecida, distinta de DPS, pode entrar no ledger como `VALID_FOR_ANALYSIS_NOT_AUTHORITY_CONFIRMED`, com `validityEvidence=PARSED_NFSE_DOCUMENT`. Ela compõe provisoriamente receita de serviço prestado ou compra de serviço tomado e sempre exige ressalva de que autorização e cancelamento não foram confirmados junto à autoridade. Consulte `provisional_nfse_documents`. Override `INVALID` ou `CANCELLED` exclui o documento; DPS não recebe essa validade provisória.

A consulta de regime acontece somente depois da análise documental: XMLs são lidos e deduplicados, a empresa é identificada, o ledger é construído, fornecedores e compradores são consolidados, CNPJs repetidos são reduzidos a um representante por entidade e só então `LOCAL_RFB` é consultado. CPF nunca entra nessa lista.

## PGDAS-D e DAS

`declared_revenue_periods` recebe competência civil válida `AAAA-MM`, receita declarada, fonte e DAS opcional. `revenue_reconciliation` compara a receita declarada com documentos válidos. Estados: `MATCHED`, `DECLARED_REVENUE_UNSUPPORTED`, `DOCUMENT_REVENUE_EXCEEDS_DECLARED` e `NO_DECLARED_PERIOD`.

Ausência de documento não prova falta de emissão. Apresente a diferença como receita declarada sem suporte documental e solicite conciliação de cancelamentos, devoluções, competência ou documentos ausentes.

O leitor classifica entrada e saída relativamente aos contribuintes-alvo, preserva participação como intermediário em DPS, exclui documentos que não envolvem a empresa e registra documentos com papel ambíguo.

Use `targetPartyRole` para saber quem é a empresa no documento e `targetOperation` para a direção relativa quando comprovável. Preserve `operationStatus` e `operation` como evidência do XML. Se `targetOperation` for `NAO_VERIFICAVEL`, não deduza entrada ou saída apenas pelo papel da empresa.

Quando presentes no layout, os itens também preservam NCM, CFOP, quantidade, valor unitário, valor bruto, base IBS/CBS e valores de IBS/CBS como textos decimais de origem. Não trate campos ausentes como zero.

O resumo `fiscal_profile` informa a cobertura econômica e os dez grupos mais materiais de cada dimensão. Participações financeiras usam somente itens com `grossValue`; sempre apresente a cobertura junto com qualquer percentual por valor.

O resumo `risk_profile` informa quantos grupos de achados existem por prioridade e inclui os dez primeiros. Consulte `risks` para a lista completa. Cada grupo preserva categoria, recorrência em itens e documentos, valor bruto coberto, classificações afetadas, motivos e referências amostrais. A exposição usa apenas `grossValue` disponível; ela não representa imposto devido, crédito recuperável ou autuação estimada. Não produza uma nota geral somando prioridades.

O resumo `credit_profile` avalia somente operações comprovadas como `ENTRADA`. Consulte `credits` para todos os grupos. Sem enquadramento temporal, o motor retorna `REGIME_NOT_CONFIRMED`. Simples com IBS/CBS `WITHIN_SIMPLES` não gera presunção de crédito próprio. No modo `REGULAR`, documento conforme e com valores de IBS/CBS gera no máximo `CONDITIONAL_CREDIT` até que destinação, vínculo com a atividade e operação subsequente sejam comprovados. `documentedIbsValue`, `documentedCbsValue` e `documentedTaxValue` são valores do documento, não valor de crédito.

Resultados de documentos de 2026 usam `SIMULATION_ONLY_2026`. Não os apresente como débito ou crédito com efeito jurídico real. Confira as fontes oficiais retornadas em `legal_sources` e registre a data de corte da revisão.

O resumo `output_tax_profile` cobre apenas operações comprovadas como `SAÍDA` e separa duas perspectivas:

- `output_debits`: indícios documentais de débito da empresa. `DOCUMENTED_DEBIT_INDICATION` não representa apuração, exigibilidade ou pagamento confirmado.
- `customer_credits`: efeito possível para o adquirente. `CONDITIONAL_CUSTOMER_CREDIT` depende do regime declarado, documento idôneo, extinção do débito e demais condições aplicáveis.

Se a empresa estiver no Simples `WITHIN_SIMPLES`, `SIMPLES_CUSTOMER_CREDIT_AMOUNT_PENDING` exige o montante de IBS/CBS devido por meio do regime. Não use `documentedTaxValue` nem valor bruto para estimá-lo. Quando o montante for declarado, consulte `simples_tax_amounts` e preserve `paymentStatus=NOT_ASSESSED`. Saída sem grupo IBS/CBS recebe `NO_DOCUMENTARY_INDICATION`; ausência do grupo não é não conformidade automática.

Não misture resultados de `analysis_id` diferentes. Se a análise expirar, execute novamente a pasta e use o novo identificador.

## Limite de confiança do acesso local

O servidor MCP usa transporte `stdio` local e aceita o `folder_path` informado pelo cliente. Ele opera com as permissões do usuário que executa o Codex e não mantém uma lista própria de diretórios permitidos.

- Analise somente uma pasta explicitamente indicada pelo usuário para o caso atual.
- Não tente descobrir ou percorrer outras pastas por conveniência.
- Não exponha este servidor por HTTP, SSE ou outro transporte remoto sem autenticação, autorização e uma política de diretórios permitidos.
- Em ambientes compartilhados ou não controlados, configure uma allowlist antes de habilitar acesso remoto.

## Contrato mínimo sugerido

```json
{
  "schema_version": "1.0",
  "generated_at": "2026-08-24T12:00:00-03:00",
  "period": { "from": "2026-01-01", "to": "2026-01-31" },
  "entity_ref": "empresa-001",
  "coverage": {
    "documents": 0,
    "gross_value": 0,
    "supported_documents": ["NFE", "NFSE_NATIONAL", "NFSE_ABRASF"],
    "rejected": 0,
    "unparsed": 0
  },
  "operations": [
    {
      "operation_ref": "grupo-001",
      "direction": "purchase|sale|service",
      "document_type": "NFE",
      "classification": { "ncm": null, "nbs": null, "tax_class": null },
      "operation_code": null,
      "origin_region": null,
      "destination_region": null,
      "counterparty_type": null,
      "quantity": 0,
      "gross_value": 0,
      "tax_base": 0,
      "tax_value": 0,
      "validation": { "status": "conforming|warning|error|not_applicable", "codes": [] }
    }
  ],
  "limitations": [],
  "source_hashes": []
}
```

## Regras do contrato

- Versione o esquema e rejeite versões desconhecidas sem conversão explícita.
- Informe cobertura por quantidade e valor; amostra não deve parecer universo completo.
- Preserve os códigos originais e acrescente descrições sem substituir a fonte.
- Agregue somente quando a agregação não esconder exceções materiais.
- Use referências pseudonimizadas para empresa, estabelecimento e contraparte.
- Não exporte XML completo, certificado, chave privada, token, endereço ou identificação pessoal por padrão.
- Inclua limitações do parser, leiautes não suportados, rejeições e campos ausentes.
- Valide totais exportados contra os totais exibidos pela aplicação antes de integrar.

## Validação operacional

1. Comece com uma empresa sintética ou anonimizada e um período curto.
2. Valide totais, agrupamentos, ocorrências e lacunas manualmente.
3. Gere o diagnóstico e revise os achados de maior impacto com um especialista fiscal.
4. Só então amplie documentos, períodos e empresas.
