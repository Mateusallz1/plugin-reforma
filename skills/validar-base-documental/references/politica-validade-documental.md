# Política inicial de validade documental

## Regra principal

Somente documentos identificados, coerentes, pertencentes ao escopo, não cancelados e não duplicados podem compor a base documental quantitativa.

## Estados

- `VALID_DOCUMENTARY`: NF-e/NFC-e com protocolo coerente ou NFS-e ABRASF com número, identificador de verificação, emissão, prestador, tomador e valor coerentes, sem cancelamento confirmado;
- para CT-e modelo 57, `VALID_DOCUMENTARY` exige chave, emissão, emitente, tomador, valor total da prestação e protocolo de autorização coerentes;
- `STATUS_NOT_VERIFIABLE`: documento reconhecido sem protocolo suficiente;
- `CANCELLED`: evento de cancelamento homologado e coerente com a chave;
- `INVALID_STRUCTURE`: XML ilegível ou campos estruturais essenciais inválidos;
- `UNSUPPORTED_LAYOUT`: XML reconhecível fora das famílias do piloto;
- `DUPLICATE`: chave já representada por outra ocorrência;
- `OUT_OF_PERIOD`: emissão fora da competência;
- `OUT_OF_SCOPE`: empresa não comprovada como emitente ou destinatária.

## Limites de evidência

`VALID_DOCUMENTARY` não significa situação atual confirmada na autoridade, assinatura criptográfica validada, classificação fiscal correta, direito a crédito ou conformidade tributária. Quando uma NFS-e reconhecida não trouxer situação explícita, emita `NFSE_STATUS_NOT_EMBEDDED`; a nota permanece documentalmente utilizável, mas a situação atual na prefeitura continua não confirmada.

Relatórios são fontes paralelas e opcionais. Eles podem apoiar a checagem de população, situação declarada e totais, mas não substituem detalhes ausentes do XML. Sua ausência ou divergência gera aviso, nunca rebaixa por si só uma base documental válida.

DANFE, DACTE, impressão de NFS-e e livro fiscal em PDF são representações auxiliares. Relacione-os ao XML por chave ou identificador dentro da mesma empresa, competência e direção. PDF sem XML não autoriza análise por item nem compõe totais fiscais. PDF ilegível ou sem identificador permanece como aviso de cobertura.

A direção da operação vem do papel da empresa no XML: emitente ou prestadora indica `SAIDA`; destinatária ou tomadora indica `ENTRADA`. No CT-e, use o tomador resolvido por `toma3/toma4`, não o destinatário isolado. Pastas chamadas “Entradas”, “Saídas”, “Prestados” ou “Tomados” são pistas organizacionais e divergências geram aviso sem alterar a classificação documental.

O relatório Markdown local pode apresentar a razão social (`xNome`, com `xFant` apenas como fallback do emitente) e o CNPJ da empresa-alvo. Havendo variações de nome nos XMLs, use o nome mais recorrente e gere `COMPANY_NAME_VARIATION`. Não exporte identidade de contrapartes nem inclua a identidade da empresa no JSON técnico ou na resposta conversacional.

O piloto bloqueia cada escopo por problemas documentais próprios: XML inválido, ausência de documento elegível ou documento relevante não verificável. Família não suportada ou arquivo desconhecido restringe a cobertura integral, mas não elimina escopos independentes já prontos. Nota declarada sem XML, XML sem relatório, divergência de valor e conflito entre relatório e XML permanecem como achados de checagem complementar.
