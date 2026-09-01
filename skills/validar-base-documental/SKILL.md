---
name: validar-base-documental
description: Valida uma pasta bruta ou estruturada de NF-e/NFC-e/NFS-e/CT-e, relaciona representações em PDF, discrimina operações e autoriza a análise por escopo documental antes do planejamento da Reforma Tributária. Use quando o analista indicar uma pasta empresarial e quiser decidir quais populações estão prontas; não use para calcular créditos, débitos ou concluir conformidade tributária.
---

# Validar a base documental

Execute o UC-001 antes de qualquer planejamento baseado em documentos fiscais.

## Caminho rápido padrão

Quando o usuário indicar uma pasta para validação normal:

1. A partir da raiz desta skill, execute uma vez `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run-validator.ps1 -Folder <pasta>`.
2. Leia `<pasta>\03_SAIDAS\validation-result.json` e `<pasta>\03_SAIDAS\relatorio-prontidao-documental.md`.
3. Para código de saída `0`, responda pelos artefatos e respeite `authorized_scopes`, `restricted_scopes` e `operational_analysis_required`.
4. Para código `2`, informe os escopos bloqueados e pare porque nenhuma população está autorizada.

O launcher instalado gerencia o runtime e aplica integralmente as regras do UC-001. Manutenção, atualização e testes de determinismo pertencem a tarefas explicitamente solicitadas.

Para outro código, artefato ausente ou ilegível, diagnostique a falha operacional e consulte [references/uc-001.md](references/uc-001.md) somente no ponto necessário.

## Regras documentais

1. Exija uma pasta explicitamente indicada pelo usuário. Não procure outras empresas ou diretórios.
2. Aceite tanto a estrutura UC-001 quanto uma pasta bruta explicitamente indicada. Na pasta bruta, procure recursivamente apenas dentro da raiz autorizada, ignore saídas e áreas `UC001_*`, e exija uma única empresa e competência inferíveis. Relatórios CSV/XLSX são opcionais.
3. O launcher usa `uv` somente para preparar o ambiente travado na primeira execução; chamadas seguintes usam o executável local diretamente.
4. Código de saída `0` significa ao menos um escopo pronto; código `2` significa que nenhum escopo pode prosseguir; outro código significa falha operacional.
5. Use somente `validation-result.json` e `relatorio-prontidao-documental.md` para responder. O relatório local pode identificar a empresa-alvo por razão social e CNPJ; o JSON técnico e a conversa permanecem pseudonimizados. Nunca reproduza XML bruto, chaves completas, CPF, contrapartes ou caminhos absolutos.
6. Leia [references/autorizacoes-por-escopo.md](references/autorizacoes-por-escopo.md) quando houver `restricted_scopes`. Se `planning_authorized` for falso, leia também [references/politica-validade-documental.md](references/politica-validade-documental.md), apresente os bloqueadores e pare. Se for verdadeiro com restrições, prossiga somente nos escopos autorizados e não conclua cobertura integral.
7. Leia [references/danfe-e-direcao.md](references/danfe-e-direcao.md) somente quando houver aviso de PDF ou conflito de direção. Leia [references/nfse.md](references/nfse.md) somente para explicar cobertura, validade ou aviso de NFS-e. Leia [references/cte.md](references/cte.md) somente para explicar cobertura, tomador, validade ou aviso de CT-e/DACTE. Leia [references/grupos-operacionais.md](references/grupos-operacionais.md) somente para explicar ou consumir a separação destinada à análise futura. Leia [references/uc-001.md](references/uc-001.md) somente para explicar contrato, escopo ou falha operacional. Divergências ou ausência de relatório são avisos e não bloqueiam a base documental.
8. A política vigente de população do relatório é `COMPLEMENTARY`: concilie situação e valores, mas nunca use o relatório para excluir XML documentalmente válido ou incluir nota sem XML. `WHITELIST` não está implementado.

`VALID_DOCUMENTARY` comprova apenas coerência documental local. Para NF-e/NFC-e, exige protocolo de autorização coerente; para NFS-e ABRASF, exige identificador, emissão, prestador, tomador e valor; para CT-e modelo 57, exige chave, emissão, emitente, tomador, valor da prestação e protocolo coerentes. Não representa consulta atual à autoridade, validação criptográfica da assinatura ou conformidade tributária.

Determine `ENTRADA` ou `SAIDA` pelo papel da empresa no XML: emitente/destinatária em NF-e/NFC-e, prestadora/tomadora em NFS-e e emitente/tomadora em CT-e. O nome da pasta é somente uma pista: divergências geram aviso e nunca sobrescrevem a evidência do XML. DANFE, DACTE, impressão de NFS-e e livro fiscal em PDF são evidências auxiliares; PDF sem XML não entra na base quantitativa.

Preserve `analysis_scope`, `analysis_group`, `authorized_for_planning` e `operational_analysis_required` em cada registro. Separe NFE e NFCE em entrada/saída, NFSE em prestados/tomados e CTE em prestados/tomados. Crie análise operacional somente para grupo com `COM_DOCUMENTO` e escopo autorizado; trate `SEM_DOCUMENTO` como ausência de documento no escopo, sem gerar análise vazia e sem afirmar que não houve operação: essa conclusão depende da conciliação com a declaração da competência.
