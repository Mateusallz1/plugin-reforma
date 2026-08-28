---
name: diagnosticar-reforma-tributaria
description: Analisa como uma empresa se prepara e opera diante da Reforma Tributária brasileira, mapeando classificações, riscos, créditos, lacunas de dados e cenários de simulação. Use para diagnóstico empresarial baseado em documentos fiscais e contexto operacional; não use como substituto de parecer jurídico ou contábil conclusivo.
---

# Diagnosticar a Reforma Tributária

Conduza um diagnóstico rastreável, separando dados observados, regras verificadas, hipóteses e informações ausentes. A análise de notas fiscais é uma fonte importante, mas não representa sozinha o modelo operacional da empresa.

## Escolher o modo

- **Triagem:** use quando ainda há poucos dados. Leia [references/coleta-de-dados.md](references/coleta-de-dados.md), solicite somente o bloco mínimo e entregue um mapa de lacunas e prioridades.
- **Diagnóstico:** use quando houver dados fiscais e empresariais suficientes. Leia também [references/metodologia.md](references/metodologia.md) e produza os seis blocos de análise definidos ali.
- **Preparação para simulação:** use quando o objetivo for comparar regimes, períodos ou alternativas operacionais. Exija premissas explícitas e séries mensais; não invente alíquotas, preços, margens ou comportamento de fornecedores.
- **Análise de pasta empresarial:** quando o usuário indicar uma pasta que representa uma empresa, leia [references/integracao.md](references/integracao.md), use `analyze_company_folder` e consulte os detalhes com `get_company_analysis_page`.

## Regras de evidência

1. Registre a origem e a competência de cada dado. Não misture períodos sem informar.
2. Classifique cada afirmação como `confirmado`, `indício`, `hipótese` ou `não avaliado`.
3. Diferencie falha documental, falha cadastral, risco fiscal, impacto financeiro e melhoria operacional.
4. Não trate ausência de campo como não conformidade quando o leiaute ou o período ainda não exigir esse campo.
5. Para legislação, cronogramas, leiautes e tabelas sujeitos a mudança, confira fontes oficiais atuais antes de concluir e registre a data de corte.
6. Preserve a origem dos valores. Transformações e agregações devem ser reproduzíveis.
7. Minimize dados pessoais e segredos: prefira totais, códigos, faixas e identificadores pseudonimizados. Nunca reproduza certificados, chaves privadas ou credenciais.

## Operação

1. Defina período, objetivo e responsável pela validação fiscal. Não exija CNPJ antes da primeira leitura da pasta.
2. Quando houver uma pasta empresarial explicitamente indicada, chame `analyze_company_folder` sem `target_taxpayer_ids` para permitir descoberta automática. Use `target_taxpayer_ids` somente quando o usuário confirmar uma empresa específica ou quando a descoberta retornar ambiguidade. Analise todo o período presente na pasta e não faça varredura paralela por shell.
3. Use o enriquecimento local padrão com `enrich_tax_regimes=true` e `regime_provider=LOCAL_RFB`; ele consulta `localhost:8877` e não envia dados para fora da máquina. Não peça autorização de consulta externa para esse modo. CPF nunca é consultado. Só use `PUBLIC_APIS` ou `SIMPLES_CHECK` remoto após autorização explícita. Falha local ou `UNKNOWN` não significa empresa fora do Simples.
4. Use o resumo retornado para avaliar `target_discovery`, cobertura, escopo, `party_profile`, perfil fiscal, `risk_profile`, `credit_profile`, `output_tax_profile`, `debit_extinction_profile`, `operational_ledger` e `revenue_reconciliation`. Consulte também `party_relationships`, `sales_party_types` e `regime_evidence` com `get_company_analysis_page`.
5. Se houver entradas condicionadas por falta de destinação, obtenha o `documentRef` e `itemNumber` em `documents`, colete o contexto conforme [references/coleta-de-dados.md](references/coleta-de-dados.md) e execute novamente a mesma pasta com os mesmos parâmetros mais `acquisition_contexts`. Use somente o novo `analysis_id`.
6. Se houver `SIMPLES_CUSTOMER_CREDIT_AMOUNT_PENDING`, obtenha `documentRef` e `itemNumber`, colete o montante declarado do Simples e reexecute com `simples_tax_amounts`. Use somente o novo `analysis_id`.
7. Se a conclusão depender da extinção, colete eventos com fonte pseudonimizada e reexecute com `debit_extinction_evidence`. Consulte `debit_extinctions` no novo `analysis_id`.
8. NFS-e reconhecida pode entrar como `VALID_FOR_ANALYSIS_NOT_AUTHORITY_CONFIRMED`, compondo serviços prestados ou tomados com ressalva explícita. Não a apresente como autorizada. DPS e documentos sem integridade mínima permanecem excluídos. Use `document_validity_overrides` para confirmação, invalidação ou cancelamento declarado; cancelamento identificado não pode ser reabilitado.
9. Colete receita mensal do PGDAS-D e DAS quando disponível, reexecute com `declared_revenue_periods` e consulte `revenue_reconciliation`. Diferença sem documento é lacuna de suporte, não infração presumida.
10. Faça a triagem de suficiência usando a matriz de coleta.
11. Concilie cadastro, regime informado e perfil observado nas operações.
12. Agrupe compras e vendas por classificação, tributação, natureza, UF/município, contraparte e materialidade.
13. Aplique a metodologia, mantendo cada achado ligado às evidências e aos dados faltantes.
14. Comece pelos achados de `risks`, conferindo evidência, recorrência, cobertura financeira e justificativa de prioridade. A prioridade técnica não é uma autuação confirmada nem substitui a confiança do diagnóstico.
15. Para créditos, preserve os status do motor. `REGIME_NOT_CONFIRMED` bloqueia conclusão; `CONDITIONAL_CREDIT` continua condicionado; `POTENTIAL_CREDIT` é apenas um indício preliminar com contexto declarado. Valores documentados nunca são apresentados como crédito apropriado. Em 2026, identifique `SIMULATION_ONLY_2026`.
16. Nas saídas, separe `output_debits` de `customer_credits`. Indício documental de débito não é apuração; possível crédito do cliente não é crédito apropriado. Para fornecedor no Simples `WITHIN_SIMPLES`, use somente o montante declarado em `simples_tax_amounts`; não derive do valor bruto ou do destaque do XML.
17. Em `debit_extinctions`, trate `EXTINGUISHED` apenas como conciliação matemática de evidências declaradas. Não represente como reconhecimento oficial ou apropriação confirmada.
18. Priorize ações por impacto potencial, probabilidade e urgência, sem converter automaticamente sinais em infrações.
19. Recomende simulação somente quando houver uma decisão concreta e premissas mensuráveis.

Se `analyze_company_folder` não estiver disponível, informe que a conexão local do plugin precisa ser habilitada. Não substitua silenciosamente a ferramenta por envio externo dos documentos.

## Entrega mínima

Produza:

- resumo executivo com período, escopo, data de corte e nível de confiança;
- resposta às seis perguntas de negócio;
- tabela de achados com evidência, status, impacto, ação e responsável sugerido;
- dados faltantes separados em `bloqueiam conclusão` e `melhoram precisão`;
- cenários propostos, premissas necessárias e métrica de decisão;
- limitações e pontos que exigem validação contábil ou jurídica.

Se os dados forem insuficientes, entregue a triagem e pare antes de estimar valores ou comparar regimes.
