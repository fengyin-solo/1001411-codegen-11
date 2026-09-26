"""隧道设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
import threading
from datetime import datetime, timezone
from typing import Any

from app.store import store

MODULE = "tunnel"
REQUIRED_FIELDS = ["隧道编码", "隧道名称", "隧道长度"]
STATUS_ORDER = ["待移交", "正常养护", "检修封闭", "已停用"]
ACTION_RULES = {"办理移交": "正常养护", "安排检修": "检修封闭", "停用隧道": "已停用"}
NEGATIVE_ACTIONS = ["停用隧道"]

# 台账导入材料的固定列：前四列必须齐全；照明通风可以合成一列「照明通风方式」，
# 也可以拆成「照明方式」「通风方式」两列，两种表头都认。
IMPORT_FIXED_COLUMNS = ["隧道编码", "隧道名称", "隧道长度", "断面形式"]
IMPORT_COMBINED_COLUMN = "照明通风方式"
IMPORT_SPLIT_COLUMNS = ["照明方式", "通风方式"]
IMPORT_TEMPLATE_COLUMNS = IMPORT_FIXED_COLUMNS + [IMPORT_COMBINED_COLUMN]
# 「照明通风方式」合写时的拆分分隔符：LED照明/机械通风 → 照明方式、通风方式
LV_SEPARATOR = re.compile(r"[/、,，;；|]+")
SUPPORTED_ENCODINGS = ("utf-8-sig", "gb18030")


def _decode_material(content: bytes) -> str:
    """解开材料文本：优先 UTF-8（兼容 BOM），退回 GBK，都不行就拒收。"""
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("材料编码无法识别，请使用 UTF-8 或 GBK 编码的 CSV 文件")


def _parse_material(text: str) -> tuple[list[str], list[dict[str, str]]]:
    """把材料文本解析成表头与数据行；逗号与制表符分隔都认。"""
    if not text.strip():
        raise ValueError("材料是空的，请按固定列整理后再上传")
    text = text.lstrip("\ufeff")
    first_line = text.splitlines()[0]
    delimiter = "\t" if "\t" in first_line and "," not in first_line else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = [(name or "").strip() for name in (reader.fieldnames or [])]
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({
            (key or "").strip(): (value or "").strip()
            for key, value in raw.items()
            if key is not None
        })
    return headers, rows


def _check_headers(headers: list[str]) -> None:
    """表头必须覆盖固定列，缺列时一次性说明缺了哪几列。"""
    missing = [column for column in IMPORT_FIXED_COLUMNS if column not in headers]
    if missing:
        raise ValueError(
            f"材料缺少固定列：{'、'.join(missing)}；"
            f"模板列应为：{'、'.join(IMPORT_TEMPLATE_COLUMNS)}"
        )
    has_combined = IMPORT_COMBINED_COLUMN in headers
    has_split = all(column in headers for column in IMPORT_SPLIT_COLUMNS)
    if not (has_combined or has_split):
        raise ValueError(
            f"材料缺少照明通风列：请提供「{IMPORT_COMBINED_COLUMN}」"
            f"或「{'、'.join(IMPORT_SPLIT_COLUMNS)}」两列"
        )


def _split_lighting_ventilation(text: str) -> tuple[str, str]:
    """拆开合写的照明通风方式；拆不开时整段记入照明方式，通风方式留空待补。"""
    parts = [part.strip() for part in LV_SEPARATOR.split(text, maxsplit=1)]
    parts = [part for part in parts if part]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return (parts[0] if parts else ""), ""


def _canonical_values(raw: dict[str, str]) -> dict[str, str]:
    """把一行材料归一成台账字段口径，与表头是合写还是分写无关。"""
    values = {column: raw.get(column, "") for column in IMPORT_FIXED_COLUMNS}
    if all(column in raw for column in IMPORT_SPLIT_COLUMNS):
        values["照明方式"] = raw.get("照明方式", "")
        values["通风方式"] = raw.get("通风方式", "")
    else:
        lighting, ventilation = _split_lighting_ventilation(raw.get(IMPORT_COMBINED_COLUMN, ""))
        values["照明方式"] = lighting
        values["通风方式"] = ventilation
    return values


def _parse_length(text: str) -> float | int | None:
    """隧道长度必须是有限数字；是整数就按整数落账，否则保留小数。"""
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


class TunnelService:
    def __init__(self) -> None:
        # 导入批次按材料内容哈希登记：同一份材料重复交上来只算一次
        self._import_lock = threading.Lock()
        self._import_batches: dict[str, dict[str, Any]] = {}
        self._import_order: list[str] = []

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("隧道编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"隧道设施 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于隧道设施可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"隧道设施已{action}"

    def import_ledger(self, *, filename: str, content: bytes) -> dict[str, Any]:
        """导入一份隧道台账材料。

        逐行校验（必填、长度数字、编码重复），每行各自定下收下或被拒，互不影响；
        全部校验完才在一个锁里一次性并入台账，导入中断后整批重交不会留下半条残行；
        同一份材料按内容哈希只入账一次，重复提交直接返回首次的导入结果。
        """
        digest = hashlib.sha256(content).hexdigest()
        with self._import_lock:
            existing = self._import_batches.get(digest)
            if existing is not None:
                return self._batch_view(existing, deduplicated=True)

            text = _decode_material(content)
            headers, raw_rows = _parse_material(text)
            _check_headers(headers)
            if not raw_rows:
                raise ValueError("材料里只有表头没有数据行，请补充后再上传")

            batch_id = f"IMP-{len(self._import_order) + 1:04d}"
            ledger_codes = {
                str(row.get("隧道编码", "")).strip()
                for row in store.rows(MODULE)
                if str(row.get("隧道编码", "")).strip()
            }
            taken_codes = set(ledger_codes)
            accepted_at: dict[str, int] = {}
            next_id = max((int(row.get("id", 0)) for row in store.rows(MODULE)), default=0)

            results: list[dict[str, Any]] = []
            entries: list[dict[str, Any]] = []
            duplicate_codes: list[str] = []
            for row_no, raw in enumerate(raw_rows, start=1):
                values = _canonical_values(raw)
                reasons: list[str] = []

                missing = [field for field in REQUIRED_FIELDS if not values.get(field, "").strip()]
                if missing:
                    reasons.append(f"必填字段未填：{'、'.join(missing)}")

                length_value: float | int | None = None
                length_text = values.get("隧道长度", "").strip()
                if length_text:
                    length_value = _parse_length(length_text)
                    if length_value is None:
                        reasons.append(f"隧道长度「{length_text}」不是数字")

                code = values.get("隧道编码", "").strip()
                if code and code in taken_codes:
                    if code in ledger_codes:
                        reasons.append(f"隧道编码「{code}」与台账已有记录重复")
                    else:
                        reasons.append(f"隧道编码「{code}」与本材料第 {accepted_at[code]} 行重复")
                    if code not in duplicate_codes:
                        duplicate_codes.append(code)

                if reasons:
                    results.append({"row_no": row_no, "accepted": False, "reasons": reasons, "values": values, "entry_id": None})
                    continue

                next_id += 1
                entry = {
                    "id": next_id,
                    "隧道编码": code,
                    "隧道名称": values["隧道名称"].strip(),
                    "隧道长度": length_value,
                    "断面形式": values["断面形式"].strip(),
                    "照明方式": values["照明方式"].strip(),
                    "通风方式": values["通风方式"].strip(),
                    "status": STATUS_ORDER[0],
                    "pending": True,
                    "abnormal": False,
                    "来源批次": batch_id,
                }
                entries.append(entry)
                taken_codes.add(code)
                accepted_at[code] = row_no
                shown = {field: entry[field] for field in [*IMPORT_FIXED_COLUMNS, *IMPORT_SPLIT_COLUMNS]}
                results.append({"row_no": row_no, "accepted": True, "reasons": [], "values": shown, "entry_id": next_id})

            # 原子入账：校验与组装全部完成后再一次性并入台账，要么整批入账要么不动
            store.rows(MODULE).extend(entries)
            batch = {
                "batch_id": batch_id,
                "file_hash": digest,
                "filename": filename,
                "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "total": len(raw_rows),
                "accepted": len(entries),
                "rejected": len(raw_rows) - len(entries),
                "duplicate_codes": duplicate_codes,
                "rows": results,
            }
            self._import_batches[digest] = batch
            self._import_order.append(digest)
            return self._batch_view(batch, deduplicated=False)

    def list_import_batches(self) -> list[dict[str, Any]]:
        """列出全部导入批次的摘要，最新的一批排最前。"""
        summaries = []
        for digest in reversed(self._import_order):
            batch = self._import_batches[digest]
            summaries.append({key: value for key, value in batch.items() if key != "rows"})
        return summaries

    def get_import_batch(self, batch_id: str) -> dict[str, Any] | None:
        """按批次号取一份导入结果，含逐行明细；查不到返回 None。"""
        for digest in self._import_order:
            batch = self._import_batches[digest]
            if batch["batch_id"] == batch_id:
                return self._batch_view(batch, deduplicated=False)
        return None

    @staticmethod
    def _batch_view(batch: dict[str, Any], *, deduplicated: bool) -> dict[str, Any]:
        view = dict(batch)
        view["deduplicated"] = deduplicated
        if deduplicated:
            view["message"] = f"同一份材料已导入过（批次 {batch['batch_id']}），本次未重复入账"
        else:
            view["message"] = f"导入完成：收下 {batch['accepted']} 行，被拒 {batch['rejected']} 行"
        view["ok"] = True
        return view
