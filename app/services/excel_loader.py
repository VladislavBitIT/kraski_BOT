"""Excel catalog loader implemented with a lightweight XML parser."""
from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

from app.models.catalog import CatalogData, Paint, Primer

REQUIRED_SHEETS = {"Lists", "Catalog", "Primers"}
NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
}


@dataclass(slots=True)
class ExcelLoadReport:
    categories: int
    paints: int
    primers: int
    skipped: List[str]


class CatalogValidationError(Exception):
    pass


def _column_index(cell_ref: str) -> int:
    letters = ""
    for char in cell_ref:
        if char.isalpha():
            letters += char.upper()
        else:
            break
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _parse_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    strings: List[str] = []
    for item in root.findall("main:si", NS):
        text_elems = item.findall(".//main:t", NS)
        strings.append("".join(elem.text or "" for elem in text_elems))
    return strings


def _read_sheet(zf: zipfile.ZipFile, sheet_path: str, shared_strings: List[str]) -> List[List[object]]:
    xml_data = zf.read(sheet_path)
    root = ET.fromstring(xml_data)
    rows: List[List[object]] = []
    for row in root.findall("main:sheetData/main:row", NS):
        row_values: List[object] = []
        for cell in row.findall("main:c", NS):
            ref = cell.get("r")
            if not ref:
                continue
            index = _column_index(ref)
            while len(row_values) <= index:
                row_values.append(None)
            value_node = cell.find("main:v", NS)
            value: object = None
            if value_node is not None and value_node.text is not None:
                raw = value_node.text
                if cell.get("t") == "s":
                    value = shared_strings[int(raw)]
                else:
                    try:
                        num = float(raw)
                        if num.is_integer():
                            value = int(num)
                        else:
                            value = num
                    except ValueError:
                        value = raw
            row_values[index] = value
        rows.append(row_values)
    return rows


def _sheet_rows_to_dicts(rows: List[List[object]]) -> List[Dict[str, object]]:
    if not rows:
        return []
    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    result: List[Dict[str, object]] = []
    for row in rows[1:]:
        entry: Dict[str, object] = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            value = row[idx] if idx < len(row) else None
            entry[header] = value
        result.append(entry)
    return result


def _read_workbook(path: Path) -> Dict[str, List[Dict[str, object]]]:
    with zipfile.ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relationships = {
            rel.get("Id"): rel.get("Target")
            for rel in rels_root.findall("pkg:Relationship", NS)
        }
        shared_strings = _parse_shared_strings(zf)
        sheets: Dict[str, List[Dict[str, object]]] = {}
        for sheet in workbook.findall("main:sheets/main:sheet", NS):
            name = sheet.get("name")
            rel_id = sheet.get(f"{{{NS['rel']}}}id")
            if not name or not rel_id:
                continue
            target = relationships.get(rel_id)
            if not target:
                continue
            rows = _read_sheet(zf, f"xl/{target}", shared_strings)
            sheets[name] = _sheet_rows_to_dicts(rows)
    return sheets


def _parse_packagings(value: object) -> List[float]:
    if value in (None, ""):
        return []
    parts = [p.strip() for p in str(value).split("/") if p.strip()]
    result: List[float] = []
    for part in parts:
        try:
            result.append(float(part.replace(",", ".")))
        except ValueError as exc:
            raise CatalogValidationError(f"Invalid packaging value '{part}'") from exc
    return result


def _collect_prices(row: Dict[str, object], packs: List[float]) -> Dict[float, float]:
    prices: Dict[float, float] = {}
    for size in packs:
        key_variants = [f"Price_{size:g}", f"Price_{int(size)}"]
        for key in key_variants:
            value = row.get(key)
            if value not in (None, ""):
                prices[float(size)] = float(value)
                break
    return prices


def _load_categories(rows: List[Dict[str, object]]) -> List[str]:
    categories = []
    for row in rows:
        value = row.get("Categories")
        if value not in (None, ""):
            categories.append(str(value).strip())
    return categories


def load_catalog(path: Path) -> Tuple[CatalogData, ExcelLoadReport]:
    if not path.exists():
        raise FileNotFoundError(path)

    sheets = _read_workbook(path)
    missing = REQUIRED_SHEETS - set(sheets)
    if missing:
        raise CatalogValidationError(f"Missing sheets: {', '.join(sorted(missing))}")

    categories = _load_categories(sheets["Lists"])
    paints: List[Paint] = []
    primers: List[Primer] = []
    skipped: List[str] = []

    for row in sheets["Catalog"]:
        sku = str(row.get("SKU") or "").strip()
        if not sku:
            continue
        packs = _parse_packagings(row.get("Packagings"))
        prices = _collect_prices(row, packs)
        if not prices:
            skipped.append(f"Paint {sku}: no prices")
            continue
        unit = str(row.get("PackagingUnit") or "kg").lower()
        density = row.get("Density_kg_l")
        if unit == "l" and not density:
            skipped.append(f"Paint {sku}: density required for liters")
            continue
        paint = Paint(
            sku=sku,
            brand=str(row.get("Brand") or "").strip(),
            series=str(row.get("Series") or "").strip(),
            category=str(row.get("Category") or "").strip(),
            name=str(row.get("Name") or "").strip(),
            url=str(row.get("URL") or "").strip() or None,
            unit=unit,
            packagings=packs,
            prices=prices,
            consumption_min=_to_float(row.get("Consumption_g_m2_min")),
            consumption_max=_to_float(row.get("Consumption_g_m2_max")),
            density_kg_l=_to_float(density) if density not in (None, "") else None,
        )
        paints.append(paint)

    for row in sheets["Primers"]:
        code = str(row.get("Code") or "").strip()
        if not code:
            continue
        packs = _parse_packagings(row.get("Packagings"))
        prices = _collect_prices(row, packs)
        if not prices:
            skipped.append(f"Primer {code}: no prices")
            continue
        unit = str(row.get("PackagingUnit") or "kg").lower()
        density = row.get("Density_kg_l")
        if unit == "l" and not density:
            skipped.append(f"Primer {code}: density required for liters")
            continue
        primer = Primer(
            code=code,
            name=str(row.get("Name") or "").strip(),
            unit=unit,
            packagings=packs,
            prices=prices,
            consumption_min=_to_float(row.get("Consumption_g_m2_min")),
            consumption_max=_to_float(row.get("Consumption_g_m2_max")),
            default_layers=int(row.get("Default_layers") or 1),
            density_kg_l=_to_float(density) if density not in (None, "") else None,
        )
        primers.append(primer)

    catalog = CatalogData(categories, paints, primers)
    report = ExcelLoadReport(len(categories), len(paints), len(primers), skipped)
    return catalog, report


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
