from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fiscal_document_intake.cli import main
from fiscal_document_intake.core import (
    ValidationError,
    validate_access_key,
    validate_folder,
    write_outputs,
)
from openpyxl import Workbook
from reportlab.pdfgen import canvas

COMPANY = "12345678000195"
OTHER = "98765432000198"
NAMESPACE = "http://www.portalfiscal.inf.br/nfe"
CTE_NAMESPACE = "http://www.portalfiscal.inf.br/cte"
PLUGIN_ROOT = Path(__file__).parents[2]


def access_key(issuer: str, model: str, number: int) -> str:
    base = f"352603{issuer}{model}001{number:09d}112345678"
    assert len(base) == 43
    weight = 2
    total = 0
    for digit in reversed(base):
        total += int(digit) * weight
        weight = 2 if weight == 9 else weight + 1
    check = 11 - (total % 11)
    if check >= 10:
        check = 0
    return base + str(check)


def nfe_xml(
    key: str,
    model: str,
    issuer: str,
    recipient: str,
    issue_date: str,
    amount: str,
    *,
    protocol: bool = True,
) -> str:
    issuer_name = (
        "EMPRESA SINTETICA LTDA" if issuer == COMPANY else "CONTRAPARTE SINTETICA"
    )
    recipient_name = (
        "EMPRESA SINTETICA LTDA" if recipient == COMPANY else "CONTRAPARTE SINTETICA"
    )
    protocol_xml = (
        f"""
  <protNFe versao="4.00">
    <infProt>
      <tpAmb>2</tpAmb><verAplic>TESTE</verAplic><chNFe>{key}</chNFe>
      <dhRecbto>{issue_date}T12:05:00-03:00</dhRecbto>
      <nProt>135260000000001</nProt><digVal>TESTE</digVal>
      <cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo>
    </infProt>
  </protNFe>"""
        if protocol
        else ""
    )
    root_open = (
        f'<nfeProc xmlns="{NAMESPACE}" versao="4.00">'
        if protocol
        else f'<NFe xmlns="{NAMESPACE}">'
    )
    root_close = "</nfeProc>" if protocol else "</NFe>"
    nfe_open = "<NFe>" if protocol else ""
    nfe_close = "</NFe>" if protocol else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{root_open}
{nfe_open}
  <infNFe Id="NFe{key}" versao="4.00">
    <ide><cUF>35</cUF><cNF>12345678</cNF><natOp>VENDA</natOp><mod>{model}</mod><serie>1</serie><nNF>1</nNF><dhEmi>{issue_date}T12:00:00-03:00</dhEmi><tpNF>1</tpNF></ide>
    <emit><CNPJ>{issuer}</CNPJ><xNome>{issuer_name}</xNome></emit>
    <dest><CNPJ>{recipient}</CNPJ><xNome>{recipient_name}</xNome></dest>
    <det nItem="1"><prod><cProd>1</cProd><xProd>ITEM SINTETICO</xProd><NCM>00000000</NCM><CFOP>5102</CFOP><qCom>1.00</qCom><vUnCom>{amount}</vUnCom><vProd>{amount}</vProd></prod><imposto/></det>
    <total><ICMSTot><vProd>{amount}</vProd><vNF>{amount}</vNF></ICMSTot></total>
  </infNFe>
{nfe_close}
{protocol_xml}
{root_close}
"""


def cancellation_xml(key: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<procEventoNFe xmlns="{NAMESPACE}" versao="1.00">
  <evento versao="1.00"><infEvento Id="ID110111{key}01"><cOrgao>35</cOrgao><tpAmb>2</tpAmb><CNPJ>{COMPANY}</CNPJ><chNFe>{key}</chNFe><dhEvento>2026-03-10T12:00:00-03:00</dhEvento><tpEvento>110111</tpEvento><nSeqEvento>1</nSeqEvento><verEvento>1.00</verEvento></infEvento></evento>
  <retEvento versao="1.00"><infEvento><tpAmb>2</tpAmb><verAplic>TESTE</verAplic><cOrgao>35</cOrgao><cStat>135</cStat><xMotivo>Evento registrado e vinculado a NF-e</xMotivo><chNFe>{key}</chNFe><tpEvento>110111</tpEvento><nSeqEvento>1</nSeqEvento><dhRegEvento>2026-03-10T12:01:00-03:00</dhRegEvento><nProt>135260000000002</nProt></infEvento></retEvento>
</procEventoNFe>
"""


def cte_xml(
    key: str,
    issuer: str,
    sender: str,
    destination: str,
    amount: str,
    *,
    taker_code: str = "3",
    protocol: bool = True,
) -> str:
    protocol_xml = (
        f"""
  <protCTe versao="4.00">
    <infProt>
      <tpAmb>2</tpAmb><verAplic>TESTE</verAplic><chCTe>{key}</chCTe>
      <dhRecbto>2026-03-05T12:05:00-03:00</dhRecbto>
      <nProt>135260000000003</nProt><digVal>TESTE</digVal>
      <cStat>100</cStat><xMotivo>Autorizado o uso do CT-e</xMotivo>
    </infProt>
  </protCTe>"""
        if protocol
        else ""
    )
    root_open = (
        f'<cteProc xmlns="{CTE_NAMESPACE}" versao="4.00">'
        if protocol
        else f'<CTe xmlns="{CTE_NAMESPACE}">'
    )
    root_close = "</cteProc>" if protocol else "</CTe>"
    cte_open = "<CTe>" if protocol else ""
    cte_close = "</CTe>" if protocol else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
{root_open}
{cte_open}
  <infCte Id="CTe{key}" versao="4.00">
    <ide><cUF>35</cUF><CFOP>6353</CFOP><natOp>PRESTACAO SINTETICA</natOp><mod>57</mod><serie>1</serie><nCT>1</nCT><dhEmi>2026-03-05T12:00:00-03:00</dhEmi><modal>01</modal><toma3><toma>{taker_code}</toma></toma3></ide>
    <emit><CNPJ>{issuer}</CNPJ><xNome>TRANSPORTADORA SINTETICA</xNome></emit>
    <rem><CNPJ>{sender}</CNPJ><xNome>REMETENTE SINTETICO</xNome></rem>
    <dest><CNPJ>{destination}</CNPJ><xNome>{"EMPRESA SINTETICA LTDA" if destination == COMPANY else "DESTINATARIO SINTETICO"}</xNome></dest>
    <vPrest><vTPrest>{amount}</vTPrest><vRec>{amount}</vRec><Comp><xNome>FRETE</xNome><vComp>{amount}</vComp></Comp></vPrest>
    <infCTeNorm><infCarga><vCarga>{amount}</vCarga><proPred>CARGA SINTETICA</proPred></infCarga></infCTeNorm>
    <IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>
  </infCte>
{cte_close}
{protocol_xml}
{root_close}
"""


def nfse_xml(
    notes: list[tuple[str, str, str, str, str, str | None]],
) -> str:
    rendered = []
    for number, verification, provider, recipient, amount, status in notes:
        provider_name = (
            "EMPRESA SINTETICA LTDA" if provider == COMPANY else "CONTRAPARTE SINTETICA"
        )
        recipient_name = (
            "EMPRESA SINTETICA LTDA"
            if recipient == COMPANY
            else "CONTRAPARTE SINTETICA"
        )
        status_xml = f"<Situacao>{status}</Situacao>" if status is not None else ""
        rendered.append(
            f"""
  <Nfse>
    <InfNfse Id="NFSE-{number}">
      <Numero>{number}</Numero>
      <CodigoVerificacao>{verification}</CodigoVerificacao>
      <DataEmissao>2026-03-05T12:00:00</DataEmissao>
      <Servico>
        <Valores><ValorServicos>{amount}</ValorServicos></Valores>
        <CodigoMunicipio>2211001</CodigoMunicipio>
        <ItemListaServico>14.01</ItemListaServico>
        <CodigoCnae>3314710</CodigoCnae>
        <Discriminacao>SERVICO SINTETICO</Discriminacao>
      </Servico>
      <PrestadorServico>
        <IdentificacaoPrestador><Cnpj>{provider}</Cnpj></IdentificacaoPrestador>
        <RazaoSocial>{provider_name}</RazaoSocial>
      </PrestadorServico>
      <TomadorServico>
        <IdentificacaoTomador><CpfCnpj><Cnpj>{recipient}</Cnpj></CpfCnpj></IdentificacaoTomador>
        <RazaoSocial>{recipient_name}</RazaoSocial>
      </TomadorServico>
      {status_xml}
    </InfNfse>
  </Nfse>"""
        )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<ListaNotaFiscal xmlns="http:/www.abrasf.org.br/nfse.xsd">
{"".join(rendered)}
</ListaNotaFiscal>
"""


def make_folder(
    tmp_path: Path,
    name: str = "case",
    *,
    document_families: list[str] | None = None,
) -> Path:
    folder = tmp_path / name
    (folder / "00_CONTROLE").mkdir(parents=True)
    (folder / "01_XML").mkdir()
    (folder / "02_RELATORIOS").mkdir()
    scope = {
        "schema_version": "1.0",
        "entity_ref": "EMPRESA-001",
        "establishment_ref": "ESTAB-001",
        "entity_taxpayer_ids": [COMPANY],
        "period": "2026-03",
        "objective": "VALIDATE_DOCUMENT_BASE",
        "document_families": document_families or ["NFE", "NFCE"],
        "validation_policy": "DOCUMENTARY_INITIAL",
        "report_population_policy": "COMPLEMENTARY",
        "analysis_cutoff": "2026-08-27T00:00:00-03:00",
    }
    (folder / "00_CONTROLE" / "escopo.json").write_text(
        json.dumps(scope, indent=2), encoding="utf-8"
    )
    return folder


def write_report(
    folder: Path, rows: list[dict[str, str]], *, xlsx: bool = False
) -> None:
    headers = [
        "document_type",
        "access_key",
        "issue_date",
        "declared_status",
        "gross_amount",
        "source_type",
        "source_name",
        "generated_at",
    ]
    if xlsx:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(headers)
        for row in rows:
            sheet.append([row[column] for column in headers])
        workbook.save(folder / "02_RELATORIOS" / "relatorio.xlsx")
        return
    with (folder / "02_RELATORIOS" / "relatorio.csv").open(
        "w", encoding="utf-8", newline=""
    ) as target:
        writer = csv.DictWriter(target, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def report_row(
    key: str,
    amount: str,
    *,
    document_type: str = "NFE",
    status: str = "AUTHORIZED",
) -> dict[str, str]:
    return {
        "document_type": document_type,
        "access_key": key,
        "issue_date": "2026-03-05",
        "declared_status": status,
        "gross_amount": amount,
        "source_type": "ERP_REPORT",
        "source_name": "ERP fiscal sintetico",
        "generated_at": "2026-04-01T09:00:00-03:00",
    }


def write_danfe_pdf(path: Path, keys: list[str]) -> None:
    document = canvas.Canvas(str(path))
    for index, key in enumerate(keys):
        document.drawString(72, 760, "DANFE SINTETICO")
        document.drawString(72, 730, key)
        if index < len(keys) - 1:
            document.showPage()
    document.save()


def write_nfse_pdf(path: Path, verification_codes: list[str], *, report: bool) -> None:
    document = canvas.Canvas(str(path))
    if report:
        document.drawString(72, 780, "TERMO DE ABERTURA")
        document.drawString(72, 760, "REGISTROS DE NOTAS FISCAIS DE SERVICOS")
        for index, code in enumerate(verification_codes):
            document.drawString(72, 730 - index * 20, code)
    else:
        for index, code in enumerate(verification_codes):
            document.drawString(72, 780, "NOTA FISCAL DE SERVICOS ELETRONICA")
            document.drawString(72, 760, "DADOS DA NFSE")
            document.drawString(72, 740, "CODIGO DE VERIFICACAO")
            document.drawString(72, 720, "PRESTADOR DO SERVICO")
            document.drawString(72, 700, "TOMADOR DO SERVICO")
            document.drawString(72, 680, code)
            if index < len(verification_codes) - 1:
                document.showPage()
    document.save()


def write_dacte_pdf(
    path: Path, cte_key: str, referenced_key: str | None = None
) -> None:
    document = canvas.Canvas(str(path))
    document.drawString(72, 780, "DACTE SINTETICO")
    document.drawString(72, 760, "DOCUMENTO AUXILIAR DO CONHECIMENTO DE TRANSPORTE")
    document.drawString(72, 740, cte_key)
    if referenced_key:
        document.drawString(72, 720, referenced_key)
    document.save()


def test_access_key_generation_is_valid() -> None:
    assert validate_access_key(access_key(COMPANY, "55", 1))
    assert not validate_access_key("0" * 44)


def test_ready_end_to_end_csv_is_deterministic_and_private(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "ready")
    entry_key = access_key(OTHER, "55", 1)
    sale_key = access_key(COMPANY, "65", 2)
    (folder / "01_XML" / "entrada.xml").write_text(
        nfe_xml(entry_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    (folder / "01_XML" / "saida.xml").write_text(
        nfe_xml(sale_key, "65", COMPANY, OTHER, "2026-03-06", "50.00"), encoding="utf-8"
    )
    write_report(
        folder,
        [
            report_row(entry_key, "100.00"),
            report_row(sale_key, "50.00", document_type="NFCE"),
        ],
    )

    first = validate_folder(folder)
    second = validate_folder(folder)

    assert first == second
    assert first["status"] == "DOCUMENT_BASE_READY"
    assert first["schema_version"] == "1.9.0"
    assert first["scope"]["report_population_policy"] == "COMPLEMENTARY"
    assert first["reconciliation"]["population_policy"] == "COMPLEMENTARY"
    assert first["gates"]["planning_authorized"] is True
    assert first["documents"]["included"] == 2
    assert first["documents"]["analysis_groups"]["NFE_ENTRADAS"]["count"] == 1
    assert first["documents"]["analysis_groups"]["NFCE_SAIDAS"]["count"] == 1
    assert (
        first["documents"]["analysis_groups"]["NFE_SAIDAS"]["document_status"]
        == "SEM_DOCUMENTO"
    )
    assert (
        first["documents"]["analysis_groups"]["NFE_SAIDAS"][
            "operational_analysis_required"
        ]
        is False
    )
    assert first["reconciliation"]["documented_gross_amount"] == "150.00"
    assert first["reconciliation"]["reported_population_amount"] == "150.00"
    json_path, report_path = write_outputs(first, folder / "03_SAIDAS")
    technical_output = json_path.read_text(encoding="utf-8")
    report_output = report_path.read_text(encoding="utf-8")
    assert COMPANY not in technical_output
    assert "_private_report_context" not in technical_output
    assert "EMPRESA SINTETICA LTDA" in report_output
    assert "12.345.678/0001-95" in report_output
    assert OTHER not in report_output
    assert entry_key not in technical_output + report_output
    assert sale_key not in technical_output + report_output


def test_ready_end_to_end_accepts_xlsx(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "xlsx")
    key = access_key(COMPANY, "55", 3)
    (folder / "01_XML" / "nota.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "25.00"), encoding="utf-8"
    )
    write_report(folder, [report_row(key, "25.00")], xlsx=True)
    result = validate_folder(folder)
    assert result["status"] == "DOCUMENT_BASE_READY"
    assert result["reconciliation"]["status_counts"] == {"MATCHED_VALID": 1}


def test_blocked_end_to_end_preserves_every_gap(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "blocked")
    valid_key = access_key(OTHER, "55", 10)
    cancelled_key = access_key(COMPANY, "55", 11)
    bare_key = access_key(COMPANY, "55", 12)
    out_period_key = access_key(COMPANY, "55", 13)
    out_scope_key = access_key(OTHER, "55", 14)
    report_only_key = access_key(OTHER, "55", 15)
    mismatch_key = access_key(COMPANY, "55", 16)
    conflict_key = access_key(COMPANY, "55", 17)
    xml_only_key = access_key(COMPANY, "55", 18)

    xmls = {
        "valid.xml": nfe_xml(valid_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"),
        "duplicate.xml": nfe_xml(
            valid_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"
        ),
        "cancelled.xml": nfe_xml(
            cancelled_key, "55", COMPANY, OTHER, "2026-03-05", "20.00"
        ),
        "cancel-event.xml": cancellation_xml(cancelled_key),
        "bare.xml": nfe_xml(
            bare_key, "55", COMPANY, OTHER, "2026-03-05", "30.00", protocol=False
        ),
        "out-period.xml": nfe_xml(
            out_period_key, "55", COMPANY, OTHER, "2026-02-05", "40.00"
        ),
        "out-scope.xml": nfe_xml(
            out_scope_key, "55", OTHER, "11111111000191", "2026-03-05", "50.00"
        ),
        "mismatch.xml": nfe_xml(
            mismatch_key, "55", COMPANY, OTHER, "2026-03-05", "60.00"
        ),
        "conflict.xml": nfe_xml(
            conflict_key, "55", COMPANY, OTHER, "2026-03-05", "70.00"
        ),
        "xml-only.xml": nfe_xml(
            xml_only_key, "55", COMPANY, OTHER, "2026-03-05", "80.00"
        ),
        "malformed.xml": "<nfeProc>",
    }
    for name, content in xmls.items():
        (folder / "01_XML" / name).write_text(content, encoding="utf-8")
    write_report(
        folder,
        [
            report_row(valid_key, "100.00"),
            report_row(cancelled_key, "20.00", status="CANCELLED"),
            report_row(bare_key, "30.00"),
            report_row(report_only_key, "55.00"),
            report_row(mismatch_key, "61.00"),
            report_row(conflict_key, "70.00", status="CANCELLED"),
        ],
    )

    result = validate_folder(folder)

    assert result["status"] == "DOCUMENT_BASE_BLOCKED"
    assert result["gates"]["planning_authorized"] is False
    statuses = result["reconciliation"]["status_counts"]
    assert statuses["MATCHED_VALID"] == 1
    assert statuses["MATCHED_CANCELLED"] == 1
    assert statuses["DECLARED_WITHOUT_XML"] == 1
    assert statuses["STRUCTURALLY_UNAVAILABLE_WITH_REPORT"] == 1
    assert statuses["VALUE_MISMATCH"] == 1
    assert statuses["STATUS_CONFLICT"] == 1
    assert statuses["XML_WITHOUT_REPORT"] == 1
    blocker_codes = {item["code"] for item in result["blockers"]}
    warning_codes = {item["code"] for item in result["warnings"]}
    assert "INVALID_STRUCTURE" in blocker_codes
    assert "DECLARED_WITHOUT_XML" in warning_codes
    assert "STATUS_CONFLICT" in warning_codes
    assert "VALUE_MISMATCH" in warning_codes
    assert "XML_WITHOUT_REPORT" in warning_codes
    excluded = result["documents"]["excluded_by_reason"]
    assert excluded["CANCELLED"] == 1
    assert excluded["DUPLICATE"] == 1
    assert excluded["OUT_OF_PERIOD"] == 1
    assert excluded["OUT_OF_SCOPE"] == 1
    assert excluded["STATUS_NOT_VERIFIABLE"] == 1


def test_report_is_optional_and_only_produces_warnings(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "without-report")
    key = access_key(COMPANY, "55", 20)
    (folder / "01_XML" / "nota.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "90.00"),
        encoding="utf-8",
    )

    result = validate_folder(folder)

    assert result["status"] == "DOCUMENT_BASE_READY_WITH_WARNINGS"
    assert result["gates"]["planning_authorized"] is True
    assert result["gates"]["document_analysis_ready"] is True
    assert result["gates"]["reconciliation_ready"] is False
    assert result["blockers"] == []
    warning_codes = {item["code"] for item in result["warnings"]}
    assert warning_codes == {"REPORT_MISSING", "XML_WITHOUT_REPORT"}
    assert main(["validate", str(folder)]) == 0


def test_report_population_policy_defaults_and_rejects_whitelist(
    tmp_path: Path,
) -> None:
    legacy = make_folder(tmp_path, "legacy-report-policy")
    legacy_scope_path = legacy / "00_CONTROLE" / "escopo.json"
    legacy_scope = json.loads(legacy_scope_path.read_text(encoding="utf-8"))
    legacy_scope.pop("report_population_policy")
    legacy_scope_path.write_text(json.dumps(legacy_scope), encoding="utf-8")
    key = access_key(COMPANY, "55", 24)
    (legacy / "01_XML" / "nota.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "90.00"),
        encoding="utf-8",
    )

    result = validate_folder(legacy)

    assert result["scope"]["report_population_policy"] == "COMPLEMENTARY"
    assert result["gates"]["planning_authorized"] is True

    whitelist = make_folder(tmp_path, "unsupported-whitelist")
    whitelist_scope_path = whitelist / "00_CONTROLE" / "escopo.json"
    whitelist_scope = json.loads(whitelist_scope_path.read_text(encoding="utf-8"))
    whitelist_scope["report_population_policy"] = "WHITELIST"
    whitelist_scope_path.write_text(json.dumps(whitelist_scope), encoding="utf-8")
    (whitelist / "01_XML" / "nota.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "90.00"),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="somente COMPLEMENTARY"):
        validate_folder(whitelist)


def test_raw_folder_discovers_scope_pdfs_and_directions(tmp_path: Path) -> None:
    folder = tmp_path / "raw"
    entries = folder / "NFe ENTRADAS"
    exits = folder / "NFe SAIDAS"
    entries.mkdir(parents=True)
    exits.mkdir()
    entry_key = access_key(OTHER, "55", 21)
    exit_key = access_key(COMPANY, "55", 22)
    pdf_only_key = access_key(OTHER, "55", 23)
    (entries / "entrada.xml").write_text(
        nfe_xml(entry_key, "55", OTHER, COMPANY, "2026-03-05", "110.00"),
        encoding="utf-8",
    )
    (exits / "saida.xml").write_text(
        nfe_xml(exit_key, "55", COMPANY, OTHER, "2026-03-06", "120.00"),
        encoding="utf-8",
    )
    write_danfe_pdf(entries / "danfe.pdf", [entry_key])
    write_danfe_pdf(entries / "consolidado.pdf", [entry_key, pdf_only_key])

    result = validate_folder(folder)

    assert result["scope"]["input_mode"] == "RAW_DISCOVERY"
    assert result["scope"]["period"] == "2026-03"
    assert result["status"] == "DOCUMENT_BASE_READY_WITH_WARNINGS"
    assert result["gates"]["planning_authorized"] is True
    assert result["documents"]["direction_counts"] == {"ENTRADA": 1, "SAIDA": 1}
    assert result["pdf_evidence"]["pdf_files_found"] == 2
    assert result["pdf_evidence"]["matched_document_references"] == 1
    assert result["pdf_evidence"]["status_counts"] == {
        "DANFE_MATCHED": 1,
        "DANFE_WITHOUT_XML": 1,
    }
    warning_codes = {item["code"] for item in result["warnings"]}
    assert "DANFE_WITHOUT_XML" in warning_codes
    assert "REPORT_MISSING" in warning_codes
    assert "FOLDER_DIRECTION_CONFLICT" not in warning_codes


def test_raw_folder_accepts_validated_batch_scope_override(tmp_path: Path) -> None:
    folder = tmp_path / "raw-batch"
    folder.mkdir()
    third = "11111111000191"
    fourth = "22222222000191"
    (folder / "first.xml").write_text(
        nfe_xml(
            access_key(OTHER, "55", 901),
            "55",
            OTHER,
            COMPANY,
            "2026-03-05",
            "100.00",
        ),
        encoding="utf-8",
    )
    (folder / "second.xml").write_text(
        nfe_xml(
            access_key(third, "55", 902),
            "55",
            third,
            fourth,
            "2026-03-06",
            "50.00",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="uma única empresa"):
        validate_folder(folder)
    scope = {
        "schema_version": "1.0",
        "entity_ref": "EMPRESA-LOTE",
        "establishment_ref": "ESTAB-LOTE",
        "entity_taxpayer_ids": [COMPANY],
        "period": "2026-03",
        "objective": "VALIDATE_DOCUMENT_BASE",
        "document_families": ["NFE"],
        "validation_policy": "DOCUMENTARY_INITIAL",
        "report_population_policy": "COMPLEMENTARY",
        "analysis_cutoff": "2026-03-31T23:59:59-03:00",
    }

    result = validate_folder(folder, scope_override=scope)

    assert result["scope"]["input_mode"] == "BATCH_OVERRIDE"
    assert result["scope"]["entity_ref"] == "EMPRESA-LOTE"
    assert result["scope"]["period"] == "2026-03"
    assert result["documents"]["fiscal_documents_found"] == 2
    assert result["_private_scope_identity"]["entity_taxpayer_ids"] == [COMPANY]
    json_path, _ = write_outputs(result, folder / "outputs")
    assert COMPANY not in json_path.read_text(encoding="utf-8")


def test_raw_nfse_abrasf_consolidated_documents_and_pdfs(tmp_path: Path) -> None:
    folder = tmp_path / "raw-nfse"
    provided = folder / "NFSE PRESTADOS"
    taken = folder / "NFSE TOMADOS"
    provided.mkdir(parents=True)
    taken.mkdir()
    provided_codes = ["VERIF-A001", "VERIF-A002"]
    taken_codes = ["VERIF-B001"]
    (provided / "prestados.xml").write_text(
        nfse_xml(
            [
                ("1001", provided_codes[0], COMPANY, OTHER, "200.00", None),
                ("1002", provided_codes[1], COMPANY, OTHER, "300.00", None),
            ]
        ),
        encoding="utf-8",
    )
    (taken / "tomados.xml").write_text(
        nfse_xml([("2001", taken_codes[0], OTHER, COMPANY, "150.00", None)]),
        encoding="utf-8",
    )
    write_nfse_pdf(provided / "notas.pdf", provided_codes, report=False)
    write_nfse_pdf(provided / "livro.pdf", ["1001", "1002"], report=True)
    write_nfse_pdf(taken / "notas.pdf", taken_codes, report=False)

    result = validate_folder(folder)

    assert result["scope"]["input_mode"] == "RAW_DISCOVERY"
    assert result["scope"]["period"] == "2026-03"
    assert result["scope"]["document_families"] == ["NFSE"]
    assert result["status"] == "DOCUMENT_BASE_READY_WITH_WARNINGS"
    assert result["gates"]["planning_authorized"] is True
    assert result["gates"]["item_analysis_ready"] is True
    assert result["documents"]["fiscal_documents_found"] == 3
    assert result["documents"]["included"] == 3
    assert result["documents"]["document_type_counts"] == {"NFSE": 3}
    assert result["documents"]["direction_counts"] == {
        "ENTRADA": 1,
        "SAIDA": 2,
    }
    assert result["documents"]["analysis_groups"]["NFSE_PRESTADOS"] == {
        "label": "NFS-e de serviços prestados",
        "direction": "SAIDA",
        "analysis_scope": "NFSE",
        "authorized": True,
        "document_status": "COM_DOCUMENTO",
        "operational_analysis_required": True,
        "document_types": ["NFSE"],
        "detected_count": 2,
        "count": 2,
        "gross_amount": "500.00",
    }
    assert result["documents"]["analysis_groups"]["NFSE_TOMADOS"] == {
        "label": "NFS-e de serviços tomados",
        "direction": "ENTRADA",
        "analysis_scope": "NFSE",
        "authorized": True,
        "document_status": "COM_DOCUMENTO",
        "operational_analysis_required": True,
        "document_types": ["NFSE"],
        "detected_count": 1,
        "count": 1,
        "gross_amount": "150.00",
    }
    assert result["pdf_evidence"]["status_counts"] == {
        "NFSE_PDF_MATCHED": 2,
        "NFSE_REPORT_MATCHED": 1,
    }
    assert result["pdf_evidence"]["matched_document_references"] == 3
    warning_codes = {item["code"] for item in result["warnings"]}
    assert "NFSE_STATUS_NOT_EMBEDDED" in warning_codes
    assert "REPORT_MISSING" in warning_codes
    json_path, report_path = write_outputs(result, folder / "03_SAIDAS")
    technical_output = json_path.read_text(encoding="utf-8")
    report_output = report_path.read_text(encoding="utf-8")
    assert COMPANY not in technical_output
    assert OTHER not in technical_output + report_output
    assert not any(code in technical_output + report_output for code in provided_codes)
    assert not any(code in technical_output + report_output for code in taken_codes)


def test_raw_cte_model_57_validates_taker_and_dacte(tmp_path: Path) -> None:
    folder = tmp_path / "raw-cte"
    taken = folder / "CTE TOMADOS"
    taken.mkdir(parents=True)
    key = access_key(OTHER, "57", 60)
    referenced_nfe_key = access_key(OTHER, "55", 61)
    (taken / "cte.xml").write_text(
        cte_xml(key, OTHER, OTHER, COMPANY, "450.00"), encoding="utf-8"
    )
    write_dacte_pdf(taken / "dacte.pdf", key, referenced_nfe_key)

    result = validate_folder(folder)

    assert result["status"] == "DOCUMENT_BASE_READY_WITH_WARNINGS"
    assert result["gates"]["planning_authorized"] is True
    assert result["gates"]["full_documentary_coverage_ready"] is True
    assert result["gates"]["authorized_scopes"] == ["CTE"]
    assert result["gates"]["restricted_scopes"] == []
    assert result["scope_authorizations"]["CTE"]["status"] == "READY"
    assert result["documents"]["document_type_counts"] == {"CTE": 1}
    assert result["documents"]["analysis_groups"]["CTE_TOMADOS"] == {
        "label": "CT-e de transportes tomados",
        "direction": "ENTRADA",
        "analysis_scope": "CTE",
        "authorized": True,
        "document_status": "COM_DOCUMENTO",
        "operational_analysis_required": True,
        "document_types": ["CTE"],
        "detected_count": 1,
        "count": 1,
        "gross_amount": "450.00",
    }
    record = next(
        item
        for item in result["documents"]["records"]
        if item["document_type"] == "CTE"
    )
    assert record["analysis_scope"] == "CTE"
    assert record["analysis_group"] == "CTE_TOMADOS"
    assert record["cte_taker_role"] == "DESTINATION"
    assert record["authorized_for_planning"] is True
    assert record["operational_analysis_required"] is True
    assert result["pdf_evidence"]["status_counts"] == {"DACTE_MATCHED": 1}
    json_path, report_path = write_outputs(result, folder / "03_SAIDAS")
    technical_output = json_path.read_text(encoding="utf-8")
    report_output = report_path.read_text(encoding="utf-8")
    assert key not in technical_output + report_output
    assert OTHER not in technical_output + report_output


def test_scope_authorization_allows_ready_nfse_when_nfe_scope_is_blocked(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "partial-scope"
    nfe_exits = folder / "NFE SAIDAS"
    nfse_provided = folder / "NFSE PRESTADOS"
    nfe_exits.mkdir(parents=True)
    nfse_provided.mkdir()
    key = access_key(COMPANY, "55", 62)
    (nfe_exits / "sem-protocolo.xml").write_text(
        nfe_xml(
            key,
            "55",
            COMPANY,
            OTHER,
            "2026-03-05",
            "100.00",
            protocol=False,
        ),
        encoding="utf-8",
    )
    (nfse_provided / "prestada.xml").write_text(
        nfse_xml([("5001", "VERIF-E001", COMPANY, OTHER, "200.00", "1")]),
        encoding="utf-8",
    )

    result = validate_folder(folder)

    assert result["status"] == "DOCUMENT_BASE_READY_WITH_SCOPE_LIMITATIONS"
    assert result["gates"]["planning_authorized"] is True
    assert result["gates"]["full_documentary_coverage_ready"] is False
    assert result["gates"]["authorized_scopes"] == ["NFSE"]
    assert result["gates"]["restricted_scopes"] == ["NFE_NFCE"]
    assert result["scope_authorizations"]["NFSE"]["authorized"] is True
    assert result["scope_authorizations"]["NFE_NFCE"]["authorized"] is False
    assert result["scope_authorizations"]["NFE_NFCE"]["blocker_codes"] == [
        "STATUS_NOT_VERIFIABLE"
    ]
    records = {
        record["document_type"]: record for record in result["documents"]["records"]
    }
    assert records["NFSE"]["authorized_for_planning"] is True
    assert records["NFE"]["authorized_for_planning"] is False
    restricted_group = result["documents"]["analysis_groups"]["NFE_SAIDAS"]
    assert restricted_group["document_status"] == "DOCUMENTO_RESTRITO"
    assert restricted_group["detected_count"] == 1
    assert restricted_group["operational_analysis_required"] is False
    assert main(["validate", str(folder)]) == 0


def test_analysis_groups_separate_nfe_nfce_and_nfse(tmp_path: Path) -> None:
    folder = tmp_path / "mixed-analysis-groups"
    nfe_entries = folder / "NFE ENTRADAS"
    nfce_exits = folder / "NFCE SAIDAS"
    nfse_provided = folder / "NFSE PRESTADOS"
    nfse_taken = folder / "NFSE TOMADOS"
    for path in (nfe_entries, nfce_exits, nfse_provided, nfse_taken):
        path.mkdir(parents=True, exist_ok=True)

    entry_key = access_key(OTHER, "55", 50)
    exit_key = access_key(COMPANY, "65", 51)
    (nfe_entries / "entrada.xml").write_text(
        nfe_xml(entry_key, "55", OTHER, COMPANY, "2026-03-05", "100.00"),
        encoding="utf-8",
    )
    (nfce_exits / "saida.xml").write_text(
        nfe_xml(exit_key, "65", COMPANY, OTHER, "2026-03-06", "200.00"),
        encoding="utf-8",
    )
    (nfse_provided / "prestada.xml").write_text(
        nfse_xml([("4001", "VERIF-D001", COMPANY, OTHER, "300.00", "1")]),
        encoding="utf-8",
    )
    (nfse_taken / "tomada.xml").write_text(
        nfse_xml([("4002", "VERIF-D002", OTHER, COMPANY, "400.00", "1")]),
        encoding="utf-8",
    )

    result = validate_folder(folder)

    assert result["gates"]["planning_authorized"] is True
    groups = result["documents"]["analysis_groups"]
    assert {
        code: (group["count"], group["gross_amount"]) for code, group in groups.items()
    } == {
        "NFE_ENTRADAS": (1, "100.00"),
        "NFE_SAIDAS": (0, "0.00"),
        "NFCE_ENTRADAS": (0, "0.00"),
        "NFCE_SAIDAS": (1, "200.00"),
        "NFSE_PRESTADOS": (1, "300.00"),
        "NFSE_TOMADOS": (1, "400.00"),
        "CTE_PRESTADOS": (0, "0.00"),
        "CTE_TOMADOS": (0, "0.00"),
    }
    record_groups = {
        (record["document_type"], record["direction"]): record["analysis_group"]
        for record in result["documents"]["records"]
    }
    assert record_groups == {
        ("NFE", "ENTRADA"): "NFE_ENTRADAS",
        ("NFCE", "SAIDA"): "NFCE_SAIDAS",
        ("NFSE", "SAIDA"): "NFSE_PRESTADOS",
        ("NFSE", "ENTRADA"): "NFSE_TOMADOS",
    }
    assert groups["NFE_ENTRADAS"]["operational_analysis_required"] is True
    assert groups["NFCE_ENTRADAS"]["operational_analysis_required"] is False
    assert groups["NFCE_ENTRADAS"]["document_status"] == "SEM_DOCUMENTO"
    _, report_path = write_outputs(result, folder / "03_SAIDAS")
    report = report_path.read_text(encoding="utf-8")
    assert "## Separação operacional para análise futura" in report
    assert all(code in report for code in groups)


def test_structured_nfse_cancelled_and_invalid_documents(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "nfse-statuses", document_families=["NFSE"])
    (folder / "01_XML" / "nfse.xml").write_text(
        nfse_xml(
            [
                ("3001", "VERIF-C001", COMPANY, OTHER, "100.00", "1"),
                ("3002", "VERIF-C002", COMPANY, OTHER, "200.00", "2"),
                ("3003", "", COMPANY, OTHER, "300.00", "1"),
            ]
        ),
        encoding="utf-8",
    )

    result = validate_folder(folder)

    assert result["status"] == "DOCUMENT_BASE_BLOCKED"
    assert result["gates"]["planning_authorized"] is False
    assert result["documents"]["included"] == 1
    assert result["documents"]["excluded_by_reason"] == {
        "CANCELLED": 1,
        "INVALID_STRUCTURE": 1,
    }
    blocker_codes = {item["code"] for item in result["blockers"]}
    assert "INVALID_STRUCTURE" in blocker_codes


def test_structured_folder_reports_direction_conflict_without_reclassifying_xml(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "direction-conflict")
    wrong_folder = folder / "01_XML" / "NFe SAIDAS"
    wrong_folder.mkdir()
    entry_key = access_key(OTHER, "55", 24)
    (wrong_folder / "entrada-em-pasta-errada.xml").write_text(
        nfe_xml(entry_key, "55", OTHER, COMPANY, "2026-03-05", "130.00"),
        encoding="utf-8",
    )

    result = validate_folder(folder)

    assert result["documents"]["direction_counts"] == {"ENTRADA": 1}
    assert "FOLDER_DIRECTION_CONFLICT" in {item["code"] for item in result["warnings"]}


def test_cli_writes_ready_and_blocked_outputs(tmp_path: Path) -> None:
    ready = make_folder(tmp_path, "cli-ready")
    ready_key = access_key(COMPANY, "55", 30)
    (ready / "01_XML" / "nota.xml").write_text(
        nfe_xml(ready_key, "55", COMPANY, OTHER, "2026-03-05", "10.00"),
        encoding="utf-8",
    )
    write_report(ready, [report_row(ready_key, "10.00")])
    assert main(["validate", str(ready)]) == 0
    assert (ready / "03_SAIDAS" / "validation-result.json").is_file()
    assert (ready / "03_SAIDAS" / "relatorio-prontidao-documental.md").is_file()

    blocked = make_folder(tmp_path, "cli-blocked")
    blocked_key = access_key(COMPANY, "55", 31)
    write_report(blocked, [report_row(blocked_key, "10.00")])
    assert main(["validate", str(blocked)]) == 2
    saved = json.loads(
        (blocked / "03_SAIDAS" / "validation-result.json").read_text(encoding="utf-8")
    )
    assert saved["gates"]["planning_authorized"] is False
    assert "DECLARED_WITHOUT_XML" in {item["code"] for item in saved["warnings"]}


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows launcher")
def test_launcher_prepares_production_runtime_then_runs_without_uv(
    tmp_path: Path,
) -> None:
    folder = make_folder(tmp_path, "launcher-ready")
    key = access_key(COMPANY, "55", 40)
    (folder / "01_XML" / "nota.xml").write_text(
        nfe_xml(key, "55", COMPANY, OTHER, "2026-03-05", "140.00"),
        encoding="utf-8",
    )
    runtime = tmp_path / "runtime"
    launcher = (
        PLUGIN_ROOT
        / "skills"
        / "validar-base-documental"
        / "scripts"
        / "run-validator.ps1"
    )
    environment = os.environ.copy()
    environment["FISCAL_INTAKE_ENVIRONMENT"] = str(runtime)
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(launcher),
        "-Folder",
        str(folder),
    ]

    first = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )

    assert first.returncode == 0, first.stderr
    assert (runtime / "Scripts" / "fiscal-document-intake.exe").is_file()
    site_packages = runtime / "Lib" / "site-packages"
    assert (site_packages / "pypdf").is_dir()
    assert not (site_packages / "pytest").exists()
    assert not (site_packages / "reportlab").exists()
    assert not (site_packages / "ruff").exists()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    (fake_bin / "uv.cmd").write_text("@exit /b 99\n", encoding="ascii")
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    second = subprocess.run(
        command, env=environment, capture_output=True, text=True, check=False
    )

    assert second.returncode == 0, second.stderr
