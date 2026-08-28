# Matriz de coleta de dados

Colete por competência mensal e por estabelecimento sempre que isso mudar o tratamento da operação. Marque cada item como disponível, parcial, indisponível ou não aplicável.

## Bloco mínimo para triagem

1. **Escopo:** CNPJ-base pseudonimizado, estabelecimentos abrangidos, período e objetivo da análise.
2. **Perfil:** atividades efetivamente exercidas, CNAEs, produtos e serviços relevantes, canais de venda e localização dos clientes.
3. **Regime temporal:** regime tributário por estabelecimento e intervalo; para optante do Simples, confirmar se IBS/CBS é recolhido dentro do regime, pelo regime regular ou se a opção ainda é desconhecida.
4. **Faturamento:** receita mensal, devoluções, cancelamentos, descontos e segregação por operação, produto ou serviço.
5. **Compras:** aquisições mensais, uso ou destinação, fornecedor, origem, classificação fiscal e tributos destacados.
6. **Documentos fiscais:** resultados normalizados do analisador, quantidade analisada, cobertura do período, tipos de documento, erros e campos não suportados.
7. **Objetivo decisório:** risco a reduzir, crédito documental a preservar, preço a revisar ou regime/cenário a comparar.

Sem os itens 1, 3, 4, 5 e 6, limite-se a apontar lacunas; não estime impacto financeiro.

Para a conciliação operacional, colete por competência a receita bruta do PGDAS-D, o valor do DAS e a fonte de cada número. Quando um documento não trouxer validade verificável, aceite somente relatório de sistema ou revisão declarada por `documentRef`.

## Blocos complementares

### Cadastro e estrutura

- matriz, filiais e inscrições;
- cadeia societária relevante ao escopo;
- CNAEs cadastrais versus atividades reais;
- municípios e UFs de operação;
- estabelecimentos centralizadores e centros de distribuição.

### Vendas e prestações

- NCM, NBS ou código municipal e descrição normalizada;
- CFOP ou natureza da operação;
- CST/CSOSN e classificações ligadas a IBS/CBS quando presentes;
- destino, tipo de cliente e uso informado;
- regime do cliente e forma de recolhimento do IBS/CBS, quando o efeito de crédito da saída for relevante;
- base, alíquota, valor, redução, diferimento, suspensão, isenção e devolução;
- frete, seguros, descontos, bonificações e outras parcelas do preço;
- recorrência, margem e materialidade por grupo.

### Compras, custos e créditos

- natureza e destinação: revenda, insumo, ativo, uso e consumo ou serviço;
- fornecedor, regime conhecido e localização;
- vínculo com atividade econômica e operação subsequente;
- tributos destacados, retenções, estornos e ajustes;
- pagamento, inadimplência e devoluções quando relevantes à hipótese de crédito;
- itens sem documentação, descrição genérica ou classificação divergente.

Para cada item material que permanecer condicionado, registre o `documentRef`, número do item, destinação, confirmação do vínculo com a atividade e tratamento da operação subsequente. Use somente categorias do contrato MCP; não inclua observações livres com dados pessoais.

Se o regime ou a opção IBS/CBS não estiverem comprovados na data da aquisição, registre a lacuna como bloqueadora. Não deduza o enquadramento apenas pela aparência do XML.

Para saída do Simples com cliente regular, colete separadamente o IBS e a CBS devidos por item, a competência e o tipo de fonte. Não copie o destaque do XML como se fosse o montante do Simples e não marque pagamento sem evidência própria.

Para extinção, registre referência pseudonimizada, documento/item, data, modalidade, estado pendente ou aplicado, valores de IBS/CBS e tipo de fonte. Não inclua comprovante bruto, conta bancária, token ou identificação pessoal no contrato do plugin.

### Formação de preço

- possibilidade de repasse ou revisão de preço;
- descontos condicionais e incondicionais;
- bonificações, reembolsos, royalties e receitas acessórias.

Contratos ficam fora da etapa atual. Não solicite arquivos contratuais até que essa frente seja explicitamente iniciada.

### Processos e sistemas

- responsáveis por cadastro, emissão, recebimento e apuração;
- ERP, motor fiscal e frequência de atualização de tabelas;
- controles de alteração e aprovação;
- conciliação entre documentos, estoque, financeiro e contabilidade;
- histórico de rejeições, cartas de correção e lançamentos manuais.

### Premissas para comparação

- horizonte e fases de transição;
- cenários de volume, preço, margem e mix;
- comportamento esperado de clientes e fornecedores;
- reorganizações ou mudanças operacionais planejadas que afetem as operações fiscais observadas.

Folha, investimentos e prazo de recuperação de créditos ficam fora da etapa atual.

## Qualidade e privacidade

Registre cobertura em quantidade e valor, duplicidades, documentos inválidos e reconciliação com faturamento/contabilidade. Para análise exploratória, substitua CNPJ/CPF, nomes, endereços, certificados e chaves por identificadores estáveis e preserve a tabela de correspondência fora do plugin.
