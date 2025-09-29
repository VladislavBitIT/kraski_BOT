"""Single-file DERUFA paint calculator bot."""
from __future__ import annotations

import asyncio
import base64
import logging
import re
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from math import ceil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import aiohttp
from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pydantic import BaseSettings, Field
from itertools import product


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    bot_token: str = Field(
        "7611204286:AAECcNvzNyyHQzqY5hBME8saPCt-cCcKKFo", env="BOT_TOKEN"
    )
    admin_ids: List[int] = Field(
        default_factory=lambda: [1271797882], env="ADMIN_IDS"
    )

    amo_subdomain: str = Field("", env="AMO_SUBDOMAIN")
    amo_client_id: str = Field("", env="AMO_CLIENT_ID")
    amo_client_secret: str = Field("", env="AMO_CLIENT_SECRET")
    amo_redirect_uri: str = Field("", env="AMO_REDIRECT_URI")
    amo_auth_code: str = Field("", env="AMO_AUTH_CODE")
    amo_refresh_token: str = Field("", env="AMO_REFRESH_TOKEN")
    amo_pipeline_id: int = Field(0, env="AMO_PIPELINE_ID")
    amo_status_id: int = Field(0, env="AMO_STATUS_ID")

    catalog_path: Path = Field(
        Path("/Users/vladislavplesivcev/Downloads/catalog.xlsx"), env="CATALOG_PATH"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @staticmethod
    def _parse_list(value: str) -> List[int]:
        return [int(v.strip()) for v in value.split(",") if v.strip()]

    @classmethod
    def parse_admin_ids(cls, value: str | List[int]) -> List[int]:
        if isinstance(value, list):
            return value
        return cls._parse_list(value)

    @classmethod
    def customise_sources(cls, init_settings, env_settings, file_secret_settings):
        return (
            init_settings,
            env_settings,
            file_secret_settings,
        )

    def __init__(self, **values: Any):
        if "admin_ids" in values and isinstance(values["admin_ids"], str):
            values["admin_ids"] = self._parse_list(values["admin_ids"])
        super().__init__(**values)


# ---------------------------------------------------------------------------
# Text constants
# ---------------------------------------------------------------------------

WELCOME_TEXT = (
    "Здравствуйте! 👋 В этом боте можно **быстро рассчитать краску** под вашу задачу: "
    "подберём фасовку, посчитаем стоимость и при необходимости добавим грунты. "
    "Нажмите **Выбрать категорию**, чтобы начать."
)

HELP_TEXT = (
    "Бот помогает подобрать краску и грунты DERUFA. "
    "Начните со команды /start или выберите категорию из меню."
)

CATEGORY_PROMPT = "Выберите категорию материала:"
PAINT_LIST_HEADER = "Выберите модель краски из категории"
AREA_PROMPT = "Какая площадь покраски (м²)?"
AREA_ERROR = "Пожалуйста, введите положительное число. Например: 36.5"
PHONE_ERROR = "Похоже, номер в неверном формате. Пример: +7 900 123-45-67"
NO_PACKAGES_ERROR = (
    "Для выбранной модели не найдены доступные фасовки с ценой. "
    "Пожалуйста, выберите другую модель или обновите прайс (/admin_excel)."
)
LEAD_SUCCESS = (
    "Заявка отправлена! Наш менеджер свяжется с вами по номеру {phone}. Спасибо!"
)
LEAD_ERROR = "Не удалось отправить заявку. Попробуйте позже или обратитесь к администратору."
DEEPLINK_COPIED = "Ссылка на модель скопирована 👌 Можете делиться!"
EXCEL_SUCCESS = "Готово! Обновлено: {paints} красок, {primers} грунтов. Пропущено: {skipped}."
EXCEL_ERROR = "Не удалось обработать файл: {message}"


# ---------------------------------------------------------------------------
# Catalog models
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PackagingPrice:
    """Price information for a single packaging size."""

    size: float
    price: float


@dataclass(slots=True)
class Paint:
    """Represents a paint product that can be selected inside the bot."""

    sku: str
    brand: str
    series: str
    category: str
    name: str
    url: Optional[str]
    unit: str
    packagings: List[float]
    prices: Dict[float, float]
    consumption_min: Optional[float]
    consumption_max: Optional[float]
    density_kg_l: Optional[float] = None

    def get_consumption_average(self) -> float:
        values = [v for v in (self.consumption_min, self.consumption_max) if v]
        if not values:
            raise ValueError(f"Consumption values are missing for paint {self.sku}")
        return sum(values) / len(values)

    def available_packagings(self) -> List[float]:
        return [size for size in self.packagings if size in self.prices]


@dataclass(slots=True)
class Primer:
    """Represents a primer product that can be optionally calculated."""

    code: str
    name: str
    unit: str
    packagings: List[float]
    prices: Dict[float, float]
    consumption_min: Optional[float]
    consumption_max: Optional[float]
    default_layers: int = 1
    density_kg_l: Optional[float] = None

    def get_consumption_average(self) -> float:
        values = [v for v in (self.consumption_min, self.consumption_max) if v]
        if not values:
            raise ValueError(f"Consumption values are missing for primer {self.code}")
        return sum(values) / len(values)

    def available_packagings(self) -> List[float]:
        return [size for size in self.packagings if size in self.prices]


@dataclass(slots=True)
class CatalogData:
    """Container with categories, paints and primers loaded from Excel."""

    categories: List[str] = field(default_factory=list)
    paints: List[Paint] = field(default_factory=list)
    primers: List[Primer] = field(default_factory=list)

    def get_paint_by_sku(self, sku: str) -> Optional[Paint]:
        sku_lower = sku.lower()
        for paint in self.paints:
            if paint.sku.lower() == sku_lower:
                return paint
        return None

    def get_primer_by_code(self, code: str) -> Optional[Primer]:
        code_lower = code.lower()
        for primer in self.primers:
            if primer.code.lower() == code_lower:
                return primer
        return None


# ---------------------------------------------------------------------------
# Excel loader
# ---------------------------------------------------------------------------


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


def _to_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


# ---------------------------------------------------------------------------
# Catalog storage
# ---------------------------------------------------------------------------


@dataclass
class CatalogStorage:
    path: Path
    data: Optional[CatalogData] = None
    last_report: Optional[ExcelLoadReport] = None

    def load(self) -> CatalogData:
        catalog, report = load_catalog(self.path)
        self.data = catalog
        self.last_report = report
        return catalog

    def get(self) -> CatalogData:
        if not self.data:
            return self.load()
        return self.data


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


PHONE_PATTERN = re.compile(r"^\+?\d[\d\-\s\(\)]{7,}$")


def parse_float(value: str) -> Optional[float]:
    try:
        cleaned = value.replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


def validate_phone(value: str) -> bool:
    return bool(PHONE_PATTERN.match(value.strip())) if value else False


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_packages(packages: Dict[float, int], unit: str) -> str:
    parts = []
    for size, count in sorted(packages.items(), key=lambda item: (-item[1], -item[0])):
        size_str = f"{size:g} {unit}"
        parts.append(f"{count}×{size_str}")
    return " и ".join(parts)


def format_currency(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", " ")


def format_percentage(value: float) -> str:
    return f"{int(value * 100)}%"


# ---------------------------------------------------------------------------
# Packaging combination
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CombinationResult:
    packages: Dict[float, int]
    supplied_amount: float
    overfill: float
    total_price: float

    def as_pairs(self) -> List[Tuple[float, int]]:
        return list(self.packages.items())


def greedy_initial(target: float, sizes: Iterable[float]) -> Dict[float, int]:
    remaining = target
    result: Dict[float, int] = {}
    for size in sorted(sizes, reverse=True):
        if remaining <= 0:
            break
        count = int(ceil(remaining / size)) if size else 0
        if count:
            result[size] = count
            remaining -= size * count
    if remaining > 0 and sizes:
        smallest = min(sizes)
        result[smallest] = result.get(smallest, 0) + 1
    return result


def calculate_overfill(target: float, packages: Dict[float, int]) -> float:
    supplied = sum(size * count for size, count in packages.items())
    return max(0.0, supplied - target)


def optimise_combination(
    target: float,
    sizes: List[float],
    prices: Dict[float, float],
    base: Dict[float, int],
) -> CombinationResult:
    best = CombinationResult(
        packages=dict(base),
        supplied_amount=sum(size * count for size, count in base.items()),
        overfill=calculate_overfill(target, base),
        total_price=sum(prices[size] * count for size, count in base.items()),
    )

    search_space: List[List[int]] = []
    for size in sizes:
        count = base.get(size, 0)
        search_space.append(list(range(max(0, count - 2), count + 3)))

    for counts in product(*search_space):
        packages = {size: count for size, count in zip(sizes, counts) if count > 0}
        if not packages:
            continue
        supplied = sum(size * count for size, count in packages.items())
        if supplied < target:
            continue
        overfill = supplied - target
        price = sum(prices[size] * count for size, count in packages.items())
        if (overfill < best.overfill) or (
            overfill == best.overfill and price < best.total_price
        ):
            best = CombinationResult(packages, supplied, overfill, price)
    return best


def pick_optimal_combination(
    target: float,
    sizes: Iterable[float],
    prices: Dict[float, float],
) -> CombinationResult:
    sizes = sorted(set(float(size) for size in sizes if float(size) > 0), reverse=True)
    if not sizes:
        raise ValueError("No packaging sizes provided")
    missing = [size for size in sizes if size not in prices]
    if missing:
        raise ValueError(f"Missing prices for packaging sizes: {missing}")

    greedy = greedy_initial(target, sizes)
    return optimise_combination(target, sizes, prices, greedy)


# ---------------------------------------------------------------------------
# Calculation logic
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CalculationBreakdown:
    unit: str
    required_amount: float
    supplied_amount: float
    overfill_amount: float
    extra_area: float
    packages: Dict[float, int]
    total_price: float


@dataclass(slots=True)
class CalculationResult:
    paint: CalculationBreakdown
    primers: Dict[str, CalculationBreakdown]
    total_price: float


TOOL_FACTORS = {
    "roller": 1.0,
    "sprayer": 1.3,
}

SURFACE_FACTORS = {
    ("roller", "wall"): 1.0,
    ("roller", "ceiling"): 1.0,
    ("sprayer", "wall"): 1.0,
    ("sprayer", "ceiling"): 1.2,
}


def _ensure_density(unit: str, density: Optional[float], item_name: str) -> float:
    if unit == "l":
        if not density:
            raise ValueError(
                f"Density_kg_l is required for liter based item '{item_name}'"
            )
        return float(density)
    return 1.0


def _calc_consumption(cons_min: Optional[float], cons_max: Optional[float]) -> float:
    values = [v for v in (cons_min, cons_max) if v]
    if not values:
        raise ValueError("Consumption data is missing")
    return sum(values) / len(values)


def calculate_paint(
    paint: Paint,
    area_m2: float,
    tool: str,
    surface: str,
    reserve: float,
) -> CalculationBreakdown:
    layers = 2
    tool_factor = TOOL_FACTORS[tool]
    surface_factor = SURFACE_FACTORS[(tool, surface)]

    base_consumption = _calc_consumption(paint.consumption_min, paint.consumption_max)
    adjusted_consumption = base_consumption * tool_factor * surface_factor
    required_grams = area_m2 * layers * adjusted_consumption * (1 + reserve)

    density_factor = _ensure_density(paint.unit, paint.density_kg_l, paint.sku)
    if paint.unit == "kg":
        required_units = required_grams / 1000
        supplied_to_grams = 1000
    else:
        required_units = (required_grams / 1000) / density_factor
        supplied_to_grams = density_factor * 1000

    combination = pick_optimal_combination(
        required_units, paint.available_packagings(), paint.prices
    )

    supplied_units = combination.supplied_amount
    supplied_grams = supplied_units * supplied_to_grams
    extra_area = max(
        0.0, (supplied_grams - required_grams) / (adjusted_consumption * layers)
    )

    return CalculationBreakdown(
        unit=paint.unit,
        required_amount=required_units,
        supplied_amount=supplied_units,
        overfill_amount=combination.overfill,
        extra_area=extra_area,
        packages=combination.packages,
        total_price=combination.total_price,
    )


def calculate_primer(primer: Primer, area_m2: float) -> CalculationBreakdown:
    layers = primer.default_layers or 1
    base_consumption = _calc_consumption(primer.consumption_min, primer.consumption_max)
    required_grams = area_m2 * layers * base_consumption
    density_factor = _ensure_density(primer.unit, primer.density_kg_l, primer.code)

    if primer.unit == "kg":
        required_units = required_grams / 1000
        supplied_to_grams = 1000
    else:
        required_units = (required_grams / 1000) / density_factor
        supplied_to_grams = density_factor * 1000

    combination = pick_optimal_combination(
        required_units, primer.available_packagings(), primer.prices
    )
    supplied_units = combination.supplied_amount
    supplied_grams = supplied_units * supplied_to_grams
    extra_area = max(
        0.0, (supplied_grams - required_grams) / (base_consumption * layers)
    )

    return CalculationBreakdown(
        unit=primer.unit,
        required_amount=required_units,
        supplied_amount=supplied_units,
        overfill_amount=combination.overfill,
        extra_area=extra_area,
        packages=combination.packages,
        total_price=combination.total_price,
    )


def calculate_total(
    paint: Paint,
    primers: Iterable[Primer],
    area_m2: float,
    tool: str,
    surface: str,
    reserve: float,
) -> CalculationResult:
    paint_breakdown = calculate_paint(paint, area_m2, tool, surface, reserve)
    primer_breakdowns: Dict[str, CalculationBreakdown] = {}
    for primer in primers:
        primer_breakdowns[primer.code] = calculate_primer(primer, area_m2)

    total = paint_breakdown.total_price + sum(
        breakdown.total_price for breakdown in primer_breakdowns.values()
    )
    return CalculationResult(paint_breakdown, primer_breakdowns, total)


# ---------------------------------------------------------------------------
# Deep links
# ---------------------------------------------------------------------------


PREFIX = "paint_"


def encode_payload(sku: str) -> str:
    payload = base64.urlsafe_b64encode(sku.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{PREFIX}{payload}"


def decode_payload(payload: Optional[str]) -> Optional[str]:
    if not payload or not payload.startswith(PREFIX):
        return None
    encoded = payload[len(PREFIX) :]
    padding = "=" * (-len(encoded) % 4)
    try:
        return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# amoCRM client
# ---------------------------------------------------------------------------


LOGGER = logging.getLogger(__name__)


class AmoAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class AmoCredentials:
    domain: str
    client_id: str
    client_secret: str
    redirect_uri: str
    refresh_token: str
    access_token: Optional[str] = None
    token_expires_at: float = 0.0

    def api_base(self) -> str:
        return f"https://{self.domain}/api/v4"


class AmoCRMClient:
    def __init__(self, credentials: AmoCredentials) -> None:
        self._cred = credentials
        self._lock = asyncio.Lock()

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        await self.ensure_access_token()
        headers = kwargs.setdefault("headers", {})
        headers["Authorization"] = f"Bearer {self._cred.access_token}"
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, **kwargs) as response:
                if response.status == 401:
                    LOGGER.info("Access token expired, refreshing")
                    await self.refresh_token()
                    headers["Authorization"] = f"Bearer {self._cred.access_token}"
                    async with session.request(method, url, **kwargs) as retry:
                        retry.raise_for_status()
                        return await retry.json()
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                return await response.text()

    async def ensure_access_token(self) -> None:
        async with self._lock:
            if self._cred.access_token and time.time() < self._cred.token_expires_at - 60:
                return
            await self.refresh_token()

    async def refresh_token(self) -> None:
        LOGGER.debug("Refreshing amoCRM access token")
        async with aiohttp.ClientSession() as session:
            payload = {
                "client_id": self._cred.client_id,
                "client_secret": self._cred.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self._cred.refresh_token,
                "redirect_uri": self._cred.redirect_uri,
            }
            async with session.post(
                f"https://{self._cred.domain}/oauth2/access_token", json=payload
            ) as response:
                if response.status >= 400:
                    text = await response.text()
                    raise AmoAuthError(f"Unable to refresh token: {response.status} {text}")
                data = await response.json()
        self._cred.access_token = data["access_token"]
        self._cred.refresh_token = data.get("refresh_token", self._cred.refresh_token)
        self._cred.token_expires_at = time.time() + int(data.get("expires_in", 3600))
        if api_domain := data.get("api_domain"):
            self._cred.domain = api_domain.replace("https://", "").rstrip("/")

    async def create_lead_with_contact(
        self,
        contact_name: str,
        phone: str,
        lead_name: str,
        price: float,
        pipeline_id: int,
        status_id: int,
        note: str,
        tags: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        payload = [
            {
                "name": lead_name,
                "price": price,
                "pipeline_id": pipeline_id,
                "status_id": status_id,
                "_embedded": {
                    "contacts": [
                        {
                            "name": contact_name,
                            "custom_fields_values": [
                                {
                                    "field_code": "PHONE",
                                    "values": [{"value": phone}],
                                }
                            ],
                        }
                    ]
                },
            }
        ]
        if tags:
            payload[0]["_embedded"]["tags"] = [{"name": tag} for tag in tags]
        response = await self._request(
            "POST",
            f"{self._cred.api_base()}/leads/complex",
            json=payload,
        )
        lead = response["_embedded"]["leads"][0]
        lead_id = lead["id"]
        await self._request(
            "POST",
            f"{self._cred.api_base()}/leads/{lead_id}/notes",
            json=[{"note_type": "common", "params": {"text": note}}],
        )
        return lead


# ---------------------------------------------------------------------------
# Keyboards
# ---------------------------------------------------------------------------


def back_keyboard(callback: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data=callback)
    builder.adjust(1)
    return builder


def single_button(text: str, callback: str) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text=text, callback_data=callback)
    builder.adjust(1)
    return builder


def categories_keyboard(categories: List[str], prefix: str = "cat") -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.button(text=category, callback_data=f"{prefix}:{category}")
    builder.adjust(1)
    return builder


def paint_actions_keyboard(sku: str, url: str | None) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Рассчитать", callback_data=f"paint:{sku}")
    builder.button(text="Скопировать ссылку", callback_data=f"share:{sku}")
    if url:
        builder.button(text="Открыть на сайте", url=url)
    builder.adjust(1)
    return builder


def color_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Ещё не выбран", callback_data="color:none")
    builder.button(text="Ввести номер", callback_data="color:manual")
    builder.adjust(1)
    return builder


def tool_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Валик", callback_data="tool:roller")
    builder.button(text="Краскопульт", callback_data="tool:sprayer")
    builder.adjust(1)
    return builder


def reserve_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    for pct in (0, 5, 10, 15):
        builder.button(text=f"{pct}%", callback_data=f"reserve:{pct}")
    builder.adjust(2)
    return builder


def surface_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Стена", callback_data="surface:wall")
    builder.button(text="Потолок", callback_data="surface:ceiling")
    builder.adjust(1)
    return builder


def primer_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Считать только краску", callback_data="primer:none")
    builder.button(text="Добавить грунт", callback_data="primer:ground")
    builder.button(text="Добавить праймер", callback_data="primer:qbase")
    builder.button(text="Добавить оба", callback_data="primer:both")
    builder.adjust(1)
    return builder


# ---------------------------------------------------------------------------
# FSM states
# ---------------------------------------------------------------------------


class LeadStates(StatesGroup):
    full_name = State()
    phone = State()
    done = State()


class CalculatorStates(StatesGroup):
    start = State()
    category_select = State()
    paint_select = State()
    q1_color = State()
    q2_area = State()
    q3_tool = State()
    q4_reserve = State()
    q5_surface = State()
    q6_primers = State()
    result = State()


class AdminStates(StatesGroup):
    waiting_excel = State()


STATE_SEQUENCE = [
    CalculatorStates.q1_color,
    CalculatorStates.q2_area,
    CalculatorStates.q3_tool,
    CalculatorStates.q4_reserve,
    CalculatorStates.q5_surface,
    CalculatorStates.q6_primers,
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


start_router = Router()


@start_router.message(CommandStart())
async def cmd_start(
    message: Message, command: CommandObject | None = None, state: FSMContext | None = None
) -> None:
    payload = None
    if command and command.args:
        payload = decode_payload(command.args)
        if payload:
            if state:
                await state.update_data(sku=payload)
    await message.answer(WELCOME_TEXT)


@start_router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


catalog_router = Router()
calc_router = Router()
questions_router = Router()
navigation_router = Router()


lead_router = Router()


def _get_amo_client(data: Dict[str, object]) -> AmoCRMClient:
    return data["amo_client"]  # type: ignore[return-value]


def _get_settings(data: Dict[str, object]) -> Settings:
    return data["settings"]  # type: ignore[return-value]


@lead_router.callback_query(F.data == "lead:start")
async def lead_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(LeadStates.full_name)
    await callback.message.answer("Введите ваше ФИО")


@lead_router.message(LeadStates.full_name)
async def lead_full_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Имя слишком короткое. Попробуйте ещё раз.")
        return
    await state.update_data(lead_full_name=text)
    await state.set_state(LeadStates.phone)
    await message.answer("Введите номер телефона")


@lead_router.message(LeadStates.phone)
async def lead_phone(message: Message, state: FSMContext, data: Dict[str, object]) -> None:
    phone = (message.text or "").strip()
    if not validate_phone(phone):
        await message.answer(PHONE_ERROR)
        return
    await state.update_data(lead_phone=phone)
    amo = _get_amo_client(data)
    settings = _get_settings(data)
    user_data = await state.get_data()
    note = user_data.get("calc_result", "")
    sku = user_data.get("sku", "")
    paint_name = user_data.get("paint_name", sku)
    lead_name = f"{sku} · {paint_name}" if sku else paint_name or "Заявка из бота"
    price = user_data.get("calc_price", 0)
    try:
        await amo.create_lead_with_contact(
            contact_name=user_data.get("lead_full_name", "Клиент"),
            phone=phone,
            lead_name=lead_name,
            price=price,
            pipeline_id=settings.amo_pipeline_id,
            status_id=settings.amo_status_id,
            note=note,
            tags=["TelegramBot", "РасчётКраски"],
        )
    except Exception:
        await message.answer(LEAD_ERROR)
    else:
        await message.answer(LEAD_SUCCESS.format(phone=phone))
    finally:
        await state.set_state(LeadStates.done)


admin_router = Router()


def _is_admin(user_id: int, data: Dict[str, object]) -> bool:
    settings: Settings | None = data.get("settings")  # type: ignore[assignment]
    if not settings:
        return False
    return int(user_id) in getattr(settings, "admin_ids", [])


@admin_router.message(Command("admin_excel"))
async def admin_excel(message: Message, state: FSMContext, data: Dict[str, object]) -> None:
    if not _is_admin(message.from_user.id, data):  # type: ignore[arg-type]
        await message.answer("Недостаточно прав для выполнения команды.")
        return
    await state.set_state(AdminStates.waiting_excel)
    await message.answer("Отправьте Excel-файл (xlsx) с каталогом.")


@admin_router.message(AdminStates.waiting_excel)
async def admin_excel_upload(
    message: Message, state: FSMContext, data: Dict[str, object]
) -> None:
    if not message.document:
        await message.answer("Нужно отправить файл в формате .xlsx")
        return
    storage: CatalogStorage = data["catalog_storage"]  # type: ignore[assignment]
    file = await message.bot.get_file(message.document.file_id)
    destination = storage.path
    temp_path = Path(destination).with_suffix(".upload.xlsx")
    await message.bot.download_file(file.file_path, destination=temp_path)
    try:
        storage.path = temp_path
        _, report = storage.load()
        temp_path.replace(destination)
        await message.answer(
            EXCEL_SUCCESS.format(
                paints=report.paints,
                primers=report.primers,
                skipped=", ".join(report.skipped) or "0",
            )
        )
    except CatalogValidationError as exc:
        await message.answer(EXCEL_ERROR.format(message=str(exc)))
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        storage.path = destination
        await state.clear()


# ---------------------------------------------------------------------------
# Dispatcher wiring
# ---------------------------------------------------------------------------


def create_dispatcher(settings: Settings) -> "Dispatcher":
    from aiogram import Dispatcher

    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)

    catalog_storage = CatalogStorage(Path(settings.catalog_path))
    try:
        catalog_storage.load()
    except FileNotFoundError:
        LOGGER.warning("Catalog file not found: %s", settings.catalog_path)
    except Exception:
        LOGGER.exception("Unable to load catalog")

    amo_credentials = AmoCredentials(
        domain=settings.amo_subdomain,
        client_id=settings.amo_client_id,
        client_secret=settings.amo_client_secret,
        redirect_uri=settings.amo_redirect_uri,
        refresh_token=settings.amo_refresh_token,
    )
    amo_client = AmoCRMClient(amo_credentials)

    dispatcher.include_router(start_router)
    dispatcher.include_router(catalog_router)
    dispatcher.include_router(calc_router)
    dispatcher.include_router(lead_router)
    dispatcher.include_router(admin_router)
    dispatcher.include_router(navigation_router)

    dispatcher.workflow_data.update(
        {
            "catalog_storage": catalog_storage,
            "settings": settings,
            "amo_client": amo_client,
        }
    )
    return dispatcher


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
    dispatcher = create_dispatcher(settings)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
