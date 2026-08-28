# CT-e no UC-001

## Cobertura inicial

O motor reconhece `cteProc` e `CTe` no namespace `http://www.portalfiscal.inf.br/cte`, leiaute 4.00 e modelo 57. A cobertura exige que a empresa-alvo seja emitente ou tomadora identificável.

Não considere suportados por aproximação: CT-e OS, eventos de CT-e, outros modelos ou documentos em que a empresa apareça somente como participante incidental. Mantenha esses casos como restrição do escopo `CTE` até existir parser e teste próprios.

## Elegibilidade documental

Um CT-e pode receber `VALID_DOCUMENTARY` quando possuir:

- chave de acesso válida e coerente com o emitente;
- modelo 57;
- data de emissão válida;
- emitente e tomador identificáveis;
- valor total da prestação válido;
- protocolo `cStat=100`, chave correspondente e número de protocolo.

A validação continua local: não consulta situação atual na autoridade, não verifica assinatura criptográfica e não valida XSD oficial.

## Tomador e direção

Resolva `toma3/toma` pelos papéis do XML: `0` remetente, `1` expedidor, `2` recebedor e `3` destinatário. Para `toma4`, use a identificação explícita do tomador.

- empresa-alvo como emitente: `SAIDA`, grupo `CTE_PRESTADOS`;
- empresa-alvo como tomadora: `ENTRADA`, grupo `CTE_TOMADOS`;
- empresa nos dois papéis: `BOTH` e `NAO_CLASSIFICADO`;
- tomador não identificável: documento inválido para este piloto.

Não force a direção pelo destinatário isolado ou pelo nome da pasta.

## DACTE

O DACTE é evidência auxiliar. Associe-o ao CT-e pela chave de acesso, sem tratar chaves de NF-e referenciadas no transporte como chave do próprio CT-e.

- `DACTE_MATCHED`: ao menos um CT-e correspondente foi associado;
- `DACTE_WITHOUT_XML`: o PDF parece DACTE, mas nenhum CT-e correspondente foi encontrado;
- `DACTE_DIRECTION_CONFLICT`: a pista do diretório diverge do papel comprovado no XML.

DACTE sem XML gera aviso e não entra na população quantitativa.
