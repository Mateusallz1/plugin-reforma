# Plano de implementação

## Objetivo do primeiro ciclo

Produzir um diagnóstico assistido e rastreável que complemente o Analisador da Reforma Tributária. O primeiro ciclo não calcula automaticamente uma “melhor opção tributária” e não emite parecer conclusivo.

## Fluxo operacional

1. **Abrir um caso:** definir empresa, estabelecimentos, período, pergunta decisória e responsável fiscal.
2. **Coletar o mínimo:** preencher a matriz de cadastro, regime, receitas, compras, documentos e objetivo.
3. **Analisar a pasta:** usar o MCP local para receber cobertura, documentos normalizados, perfil fiscal, matriz de riscos e limitações.
4. **Avaliar suficiência:** separar dados que bloqueiam conclusão dos que apenas aumentam precisão.
5. **Diagnosticar:** responder às seis perguntas, ligar achados às fontes e atribuir confiança.
6. **Validar:** revisão humana fiscal/contábil dos achados de maior impacto.
7. **Simular:** somente cenários aprovados, com premissas documentadas e comparação reproduzível.

## Piloto recomendado

Use uma empresa sintética ou dados anonimizados, um estabelecimento e um mês. Escolha uma operação predominante e uma exceção relevante. O piloto é aprovado quando:

- totais do JSON conciliam com a aplicação;
- nenhum dado pessoal ou segredo é exportado;
- todos os achados apontam evidência ou lacuna;
- o plugin se abstém quando faltam dados críticos;
- um especialista consegue confirmar ou rejeitar cada achado.

## Decisões ainda necessárias

- fonte e formato dos dados cadastrais e contábeis complementares;
- público usuário e responsável pela conclusão;
- regimes e perfis empresariais prioritários;
- período legislativo/data de corte a suportar primeiro;
- indicadores financeiros das futuras simulações;
- regras e fontes necessárias para a análise de créditos na etapa seguinte.

## Próxima entrega técnica

Adicionar cadastro temporal de clientes e fornecedores, classificação conservadora de pessoa física/condomínio/governo e exposição comercial parametrizada. Depois, implementar cenários versionados para Simples completo e híbrido sem hardcodar percentuais ocultos.
