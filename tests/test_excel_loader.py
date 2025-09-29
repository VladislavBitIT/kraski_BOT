from __future__ import annotations

from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

import pytest

from app.services import excel_loader


def column_letter(index: int) -> str:
    result = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_workbook(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    shared_strings: dict[str, int] = {}
    shared_list: list[str] = []

    for rows in sheets.values():
        for row in rows:
            for value in row:
                if isinstance(value, str) and value not in shared_strings:
                    shared_strings[value] = len(shared_list)
                    shared_list.append(value)

    def get_shared(value: str) -> int:
        return shared_strings[value]

    with zipfile.ZipFile(path, "w") as zf:
        content = ET.Element("Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types")
        ET.SubElement(
            content,
            "Override",
            PartName="/xl/workbook.xml",
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
        )
        for idx in range(len(sheets)):
            ET.SubElement(
                content,
                "Override",
                PartName=f"/xl/worksheets/sheet{idx + 1}.xml",
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            )
        if shared_list:
            ET.SubElement(
                content,
                "Override",
                PartName="/xl/sharedStrings.xml",
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml",
            )
        ET.SubElement(
            content,
            "Default",
            Extension="rels",
            ContentType="application/vnd.openxmlformats-package.relationships+xml",
        )
        ET.SubElement(
            content,
            "Default",
            Extension="xml",
            ContentType="application/xml",
        )
        zf.writestr("[Content_Types].xml", ET.tostring(content, encoding="utf-8", xml_declaration=True))

        rels = ET.Element(
            "Relationships",
            xmlns="http://schemas.openxmlformats.org/package/2006/relationships",
        )
        ET.SubElement(
            rels,
            "Relationship",
            Id="rId1",
            Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument",
            Target="xl/workbook.xml",
        )
        zf.writestr("_rels/.rels", ET.tostring(rels, encoding="utf-8", xml_declaration=True))

        workbook = ET.Element(
            "workbook",
            xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            attrib={"xmlns:r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
        )
        sheets_elem = ET.SubElement(workbook, "sheets")
        for idx, (name, _) in enumerate(sheets.items(), start=1):
            ET.SubElement(
                sheets_elem,
                "sheet",
                name=name,
                sheetId=str(idx),
                attrib={"{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id": f"rId{idx}"},
            )
        zf.writestr("xl/workbook.xml", ET.tostring(workbook, encoding="utf-8", xml_declaration=True))

        workbook_rels = ET.Element(
            "Relationships",
            xmlns="http://schemas.openxmlformats.org/package/2006/relationships",
        )
        for idx in range(len(sheets)):
            ET.SubElement(
                workbook_rels,
                "Relationship",
                Id=f"rId{idx + 1}",
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet",
                Target=f"worksheets/sheet{idx + 1}.xml",
            )
        if shared_list:
            ET.SubElement(
                workbook_rels,
                "Relationship",
                Id=f"rId{len(sheets) + 1}",
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings",
                Target="sharedStrings.xml",
            )
        zf.writestr("xl/_rels/workbook.xml.rels", ET.tostring(workbook_rels, encoding="utf-8", xml_declaration=True))

        for idx, (_, rows) in enumerate(sheets.items(), start=1):
            sheet = ET.Element(
                "worksheet",
                xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                attrib={"xmlns:r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"},
            )
            sheet_data = ET.SubElement(sheet, "sheetData")
            for r_idx, row in enumerate(rows, start=1):
                row_elem = ET.SubElement(sheet_data, "row", r=str(r_idx))
                for c_idx, value in enumerate(row):
                    if value is None:
                        continue
                    cell_ref = f"{column_letter(c_idx)}{r_idx}"
                    cell = ET.SubElement(row_elem, "c", r=cell_ref)
                    if isinstance(value, str):
                        cell.set("t", "s")
                        ET.SubElement(cell, "v").text = str(get_shared(value))
                    else:
                        ET.SubElement(cell, "v").text = str(value)
            zf.writestr(
                f"xl/worksheets/sheet{idx}.xml",
                ET.tostring(sheet, encoding="utf-8", xml_declaration=True),
            )

        if shared_list:
            sst = ET.Element(
                "sst",
                xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                count=str(len(shared_list)),
                uniqueCount=str(len(shared_list)),
            )
            for item in shared_list:
                si = ET.SubElement(sst, "si")
                ET.SubElement(si, "t").text = item
            zf.writestr(
                "xl/sharedStrings.xml",
                ET.tostring(sst, encoding="utf-8", xml_declaration=True),
            )


def create_sample_excel(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.xlsx"
    sheets = {
        "Lists": [["Categories"], ["Интерьерные"]],
        "Catalog": [
            [
                "SKU",
                "Brand",
                "Series",
                "Category",
                "Name",
                "Packagings",
                "PackagingUnit",
                "Consumption_g_m2_min",
                "Consumption_g_m2_max",
                "Price_7",
                "Price_14",
            ],
            [
                "ABC",
                "DERUFA",
                "Butterfly",
                "Интерьерные",
                "Butterfly",
                "7/14",
                "kg",
                180,
                200,
                2090,
                3450,
            ],
        ],
        "Primers": [
            [
                "Code",
                "Name",
                "Packagings",
                "PackagingUnit",
                "Consumption_g_m2_min",
                "Consumption_g_m2_max",
                "Price_10",
            ],
            [
                "ACRYLGRUND",
                "Грунт",
                "10",
                "kg",
                100,
                120,
                1500,
            ],
        ],
    }
    build_workbook(path, sheets)
    return path


def test_parse_packagings():
    assert excel_loader._parse_packagings("7/14") == [7.0, 14.0]


def test_loader_skips_without_prices(tmp_path: Path):
    path = create_sample_excel(tmp_path)
    sheets = {
        "Lists": [["Categories"], ["Интерьерные"]],
        "Catalog": [
            [
                "SKU",
                "Brand",
                "Series",
                "Category",
                "Name",
                "Packagings",
                "PackagingUnit",
                "Consumption_g_m2_min",
                "Consumption_g_m2_max",
                "Price_7",
            ],
            [
                "NOPRICE",
                "DERUFA",
                "Empty",
                "Интерьерные",
                "No price",
                "7",
                "kg",
                180,
                200,
                None,
            ],
        ],
        "Primers": [
            ["Code", "Name", "Packagings", "PackagingUnit", "Consumption_g_m2_min", "Consumption_g_m2_max", "Price_10"],
            ["ACRYLGRUND", "Грунт", "10", "kg", 100, 120, 1500],
        ],
    }
    build_workbook(path, sheets)
    catalog, report = excel_loader.load_catalog(path)
    assert len(catalog.paints) == 0
    assert report.skipped


def test_loader_requires_density_for_liters(tmp_path: Path):
    path = tmp_path / "catalog_liters.xlsx"
    sheets = {
        "Lists": [["Categories"], ["Интерьерные"]],
        "Catalog": [
            [
                "SKU",
                "Brand",
                "Series",
                "Category",
                "Name",
                "Packagings",
                "PackagingUnit",
                "Consumption_g_m2_min",
                "Consumption_g_m2_max",
                "Price_10",
            ],
            [
                "LIT",
                "DERUFA",
                "Series",
                "Интерьерные",
                "Paint",
                "10",
                "l",
                180,
                200,
                1000,
            ],
        ],
        "Primers": [
            ["Code", "Name", "Packagings", "PackagingUnit", "Consumption_g_m2_min", "Consumption_g_m2_max", "Price_10"],
            ["ACRYLGRUND", "Грунт", "10", "kg", 100, 120, 1500],
        ],
    }
    build_workbook(path, sheets)
    catalog, report = excel_loader.load_catalog(path)
    assert not catalog.paints
    assert report.skipped


def test_loader_missing_sheet(tmp_path: Path):
    path = tmp_path / "broken.xlsx"
    build_workbook(path, {"Lists": [["Categories"], ["Интерьерные"]]})
    with pytest.raises(excel_loader.CatalogValidationError):
        excel_loader.load_catalog(path)
