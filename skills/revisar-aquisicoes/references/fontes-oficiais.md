# Política de fontes oficiais

## Fontes verificadas em 2026-08-31

- Receita Federal, legislação da Reforma Tributária do Consumo: LC 214/2025, LC 227/2026, Decreto 12.955/2026 e atos conjuntos;
- Receita Federal, orientações para 2026;
- Portal NF-e, Tabela de Classificação Tributária do IBS e CBS, IT 2025.002 v1.60, publicada em 23/06/2026;
- arquivo oficial `cClassTrib 2026-06-22.xlsx`, SHA-256 `1448CB63A41BDB67EA30B4E11F4DC200D9568542C6B9335B6CFF87A4FD664654`.

## Atualização

Antes de executar uma revisão, compare versão e publicação no Portal NF-e com o `snapshot_id` empacotado. Uma versão mais recente não substitui silenciosamente o snapshot: suspenda a validação legal, atualize o XLSX por fonte oficial, gere novo JSON com `refresh-official-tables.py`, revise o diff, execute os testes e publique nova versão do plugin.

O snapshot contém somente os campos necessários à validação determinística: CST, cClassTrib, vigência, tipo de alíquota, percentuais de redução, indicadores de aplicabilidade por DF-e e referência legal. O `ruleset-lock.json` registra o hash exato usado na análise.
