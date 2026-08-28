# NFS-e no UC-001

## Cobertura inicial

O motor reconhece NFS-e em leiautes ABRASF que contenham `InfNfse`, inclusive exportações municipais consolidadas sob `ListaNotaFiscal` e variações de namespace. Cada `InfNfse` vira um documento fiscal independente, ainda que várias notas estejam no mesmo XML.

Não considere suportados por aproximação: DPS ou RPS isolada, eventos municipais separados, NFS-e Nacional sem `InfNfse` e leiautes proprietários que não exponham os campos mínimos. Registre-os como leiaute não suportado até existir parser e teste próprios.

## Elegibilidade documental

Uma NFS-e pode receber `VALID_DOCUMENTARY` quando possuir:

- número da nota;
- código de verificação ou chave de acesso;
- data de emissão ou competência válida;
- prestador e tomador identificáveis;
- valor do serviço válido;
- ausência de situação explícita de cancelamento.

Se a situação não estiver no XML, emita `NFSE_STATUS_NOT_EMBEDDED`. Isso não equivale a confirmação atual na prefeitura e deve permanecer nas limitações. Situação desconhecida explícita, identificador ausente ou campo estrutural essencial inválido bloqueia o documento.

## Direção

- empresa-alvo como prestadora: `SAIDA`;
- empresa-alvo como tomadora: `ENTRADA`;
- empresa nos dois papéis: `BOTH`;
- papel não comprovável: `NAO_VERIFICAVEL`.

“Prestados” e “Tomados” no caminho são somente pistas. O XML prevalece.

Para a análise futura, uma NFS-e incluída em `SAIDA` recebe `NFSE_PRESTADOS`; em `ENTRADA`, recebe `NFSE_TOMADOS`.

## PDFs

Impressões de NFS-e podem ser associadas por código de verificação ou chave. Livros e relatórios municipais podem ser associados pelo número da nota somente depois de restringir empresa, competência e direção. PDF associado continua sendo evidência complementar; PDF sem XML não integra a população quantitativa.

Nunca exporte número, código de verificação, chave, XML bruto ou identidade de contraparte. Use apenas referências pseudonimizadas no JSON técnico e na conversa.
