# PDF fiscal e direção da operação

## DANFE, DACTE e representações de NFS-e

O DANFE, o DACTE, a impressão de NFS-e e o livro fiscal são evidências auxiliares e não substituem o XML. Extraia somente os identificadores necessários para associação local; não exporte texto bruto, chave completa, código de verificação, nomes ou identificadores tributários.

Estados:

- `DANFE_MATCHED`: todas as chaves detectadas possuem XML correspondente;
- `DANFE_WITHOUT_XML`: ao menos uma chave não possui XML no conjunto;
- `NFSE_PDF_MATCHED`: impressão de NFS-e associada aos registros XML;
- `NFSE_REPORT_MATCHED`: livro ou relatório de NFS-e associado aos registros XML;
- `NFSE_PDF_WITHOUT_XML`: PDF de NFS-e sem documento XML correspondente;
- `DACTE_MATCHED`: DACTE associado ao CT-e correspondente;
- `DACTE_WITHOUT_XML`: PDF identificado como DACTE sem CT-e correspondente;
- `DACTE_DIRECTION_CONFLICT`: pista do diretório divergente do papel da empresa no CT-e;
- `PDF_KEY_NOT_FOUND`: PDF legível sem chave reconhecida;
- `PDF_READ_ERROR`: PDF ilegível, protegido ou fora dos limites;
- `DANFE_DIRECTION_CONFLICT`: a pasta sugere direção diferente do XML.

PDFs consolidados podem apontar para várias notas. Conte referências documentais únicas para evitar dupla contagem. Em NFS-e, restrinja associações por empresa, competência e direção antes de usar número ou código de verificação.

## Entrada e saída

Classifique relativamente à empresa do escopo:

- empresa como emitente ou prestadora: `SAIDA`;
- empresa como destinatária ou tomadora: `ENTRADA`;
- empresa nos dois papéis: `BOTH`;
- papel não comprovável: `NAO_VERIFICAVEL`.

Nunca force a direção usando apenas nome de pasta, `tpNF` isolado ou presença incidental do identificador. Preserve avisos de divergência para revisão do analista.
