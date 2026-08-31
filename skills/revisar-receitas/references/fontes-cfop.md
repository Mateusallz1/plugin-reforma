# Fontes e regras de CFOP

## Snapshot oficial

- Portal NF-e, Tabela de CFOP publicada em 25/08/2026;
- arquivo `IT_2023.002_v2.00_Tabela_CFOP_indExcI.xlsx`;
- SHA-256 `B9EE2B29E5FD52F35363B4460568C2984FC294EC92BD6D0CF4AE3BA267CD917B`;
- 619 CFOPs, incluindo indicadores de devolução, retorno, anulação, remessa e exclusão de IBS/CBS.

Antes de cada execução, confirme que a publicação vigente ainda corresponde ao snapshot. Atualização exige download oficial, conferência do hash, geração com `refresh-cfop-table.py`, revisão do diff, testes e nova versão do plugin.

## Checklist do analista

O ruleset `REVENUE-CFOP-ANALYST-V1` contém os CFOPs usuais de venda e devoluções de venda fornecidos e aprovados para o piloto. Ele complementa a tabela oficial e não é exaustivo.

`ind_excluded_ibs_cbs` não equivale automaticamente a operação sem receita. Esse indicador permanece como evidência técnica para uma regra material posterior.
