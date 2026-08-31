# Campos normalizados por modelo

## NF-e e NFC-e

- identificação: `document_ref`, `item_ref`, `nItem`;
- produto: `cProd`, `cEAN`, `xProd`, `NCM`, `CEST`, `cBenef`;
- operação: `CFOP`, `uCom`, `qCom`, `vUnCom`, `vProd`, `vDesc`, `vFrete`, `vOutro`, `indTot`;
- legado: origem e CST/CSOSN do ICMS, CST de PIS, Cofins e IPI;
- IBS/CBS: CST, `cClassTrib`, base e alíquotas quando informadas.

CFOP ausente ou malformado gera observação. NCM ausente ou malformado restringe o produto; divergência Produto × NCM somente é confirmada contra catálogo `APROVADO`. CEST e `cBenef` não são universais e sua ausência não é, isoladamente, erro.

## NFS-e

- item da lista de serviços;
- CNAE;
- código municipal, quando informado;
- discriminação;
- valor do serviço;
- retenção e alíquota do ISS;
- NBS, CST IBS/CBS e `cClassTrib`, quando informados.

CNAE, item da lista e descrição não substituem NBS. O UC-002 registra `NBS_MISSING` e `CCLASSTRIB_MISSING` para revisão, sem inferir códigos.

## CT-e

- CFOP e natureza da prestação;
- modal;
- produto predominante;
- valor total;
- componentes de prestação;
- quantidade de documentos NF-e referenciados;
- CST e `cClassTrib` IBS/CBS quando informados.

Os documentos referenciados são contados, mas suas chaves não são exportadas.

## Privacidade

O resumo e o relatório usam apenas referências pseudonimizadas e contagens. O JSONL detalhado permanece na pasta local do cliente e não deve ser commitado ou reproduzido na conversa.
