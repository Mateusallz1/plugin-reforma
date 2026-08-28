# Metodologia do diagnóstico

## Escala de confiança

- **Alta:** evidência conciliada, cobertura material e regra atual verificada.
- **Média:** evidência consistente, mas parcial ou sem conciliação independente.
- **Baixa:** amostra pequena, dado declarado sem comprovação ou hipótese operacional.
- **Não avaliável:** faltam dados que bloqueiam a conclusão.

Não transforme a escala em uma nota geral artificial. Informe confiança por achado e por bloco.

## Seis blocos obrigatórios

### 1. Como a empresa está operando

Descreva fluxo de compra, transformação ou prestação, venda, emissão, recebimento, apuração e controles. Compare cadastro declarado com comportamento observado. Evidencie exceções por estabelecimento, canal e região.

### 2. Classificações e tributações predominantes

Calcule participação em quantidade e valor por classificação, natureza de operação e tratamento tributário. Mostre concentração e cauda de exceções. Não conclua predominância apenas pela contagem quando o valor levar a resultado diferente.

### 3. Falhas, pendências e riscos

Classifique achados em:

- qualidade do dado ou documento;
- classificação/cadastro;
- tratamento tributário;
- processo/controle;
- contrato/preço;
- transição e prontidão sistêmica.

Para cada achado, registre regra ou critério, evidência, abrangência, impacto potencial, urgência, confiança e ação de validação. “Risco” não equivale a infração confirmada.

### 4. Operações que geram ou impedem créditos

Mapeie aquisições e sua destinação, documentação, fornecedor, vínculo com atividade e operação subsequente. Separe `POTENTIAL_CREDIT`, `CONDITIONAL_CREDIT`, `BLOCKED_BY_DATA`, `RISK_OF_IMPEDIMENT`, `NO_DOCUMENTARY_INDICATION`, `REQUIRES_NORMATIVE_VALIDATION` e `REGIME_NOT_CONFIRMED`. Contexto empresarial declarado pode elevar um indício condicionado a potencial, mas não comprova apropriação, extinção do débito ou conciliação contábil. Nas saídas, analise separadamente indícios de débito da empresa e possíveis créditos do cliente; regime da contraparte deve ser declarado. Nunca some valor documentado ou crédito potencial como realizado sem validar regime, regra, período, destinação e documentação. Em 2026, trate IBS/CBS apenas como simulação quando o motor indicar `SIMULATION_ONLY_2026`.

### 5. Dados necessários para comparar regimes

Liste primeiro os dados que bloqueiam a comparação e depois os que refinam o resultado. Nesta etapa, uma comparação minimamente útil precisa de série mensal de receitas, compras/custos, mix, margens, localidades, benefícios, créditos documentais e efeitos de transição. Folha, investimentos, contratos e prazo de recuperação de crédito ficam fora do escopo atual e só devem ser solicitados em etapa posterior explicitamente autorizada.

### 6. Mudanças que merecem simulação

Vincule cada cenário a uma decisão. Nesta etapa, priorize mix de fornecedores, repasse de preço, localização da operação, tratamento/classificação fiscal e alteração de processo. Defina cenário-base, alternativa, período, premissas, indicadores e condição de decisão. Não modele folha, investimentos, contratos ou prazo de recuperação de crédito nesta fase.

## Priorização

Use impacto potencial, probabilidade e urgência em escala baixa/média/alta, acompanhados de justificativa. Trate materialidade financeira e recorrência separadamente: um erro raro pode ser material; um erro pequeno pode ser sistêmico.

## Registro do achado

Cada achado deve conter:

```text
ID | título | categoria | status da evidência | período | população/cobertura
fato observado | regra/critério | risco ou oportunidade | impacto potencial
dados faltantes | ação sugerida | responsável sugerido | confiança | fonte
```

Finalize com uma fila de trabalho em três horizontes: imediato, antes da próxima obrigação/implantação relevante e estrutural.
