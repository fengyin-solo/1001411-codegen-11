"""隧道设施业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import hashlib
import io
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "tunnel"
REQUIRED_FIELDS = ["隧道编码", "隧道名称", "隧道长度"]
STATUS_ORDER = ["待移交", "正常养护", "检修封闭", "已停用"]
ACTION_RULES = {"办理移交": "正常养护", "安排检修": "检修封闭", "停用隧道": "已停用"}
NEGATIVE_ACTIONS = ["停用隧道"]

# 台账导入材料的固定列，顺序与列名都不能变
IMPORT_COLUMNS = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式"]


def _is_number(text: str) -> bool:
    try:
        float(text)
    except ValueError:
        return False
    return True


def _parse_material(content: str) -> list[tuple[int, list[str]]]:
    """把材料文本解析成 (材料行号, 各列取值) 列表。

    行号从 1 开始且保留原始行号，方便对照材料定位；整行空白的不算数据行。
    首行与固定列完全一致时按表头跳过，其余行一律按数据处理。
    """
    parsed: list[tuple[int, list[str]]] = []
    reader = csv.reader(io.StringIO(content.replace("\r\n", "\n").replace("\r", "\n")))
    for line_no, cells in enumerate(reader, start=1):
        cells = [str(cell).strip() for cell in cells]
        if not any(cells):
            continue
        if line_no == 1 and cells == IMPORT_COLUMNS:
            continue
        parsed.append((line_no, cells))
    return parsed


def _fingerprint(rows: list[tuple[int, list[str]]]) -> str:
    """同一份材料算同一个指纹：只看规范化后的行列内容，与文件名、换行风格无关。"""
    digest = hashlib.sha256()
    for _, cells in rows:
        digest.update("\x1f".join(cells).encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


class TunnelService:
    def __init__(self) -> None:
        # 导入批次台账：指纹 -> 批次结果。服务重启后与内存台账一起重置，口径一致。
        self._imports: dict[str, dict[str, Any]] = {}
        self._batch_seq = 0

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

    # ---------- 台账导入 ----------

    def import_entries(self, *, content: str, filename: str | None = None) -> dict[str, Any]:
        """导入一份台账材料：逐行校验、合格行整批落库、结果留档。

        - 每行独立判定收下或被拒，一行不合格不影响其余行；
        - 同一份材料（内容指纹相同）重复提交只算第一次，直接返回首次结果；
        - 合格行先全部构造好再一次性写入台账，中断重试不会留下半条残行。
        """
        rows = _parse_material(content)
        fingerprint = _fingerprint(rows)
        known = self._imports.get(fingerprint)
        if known is not None:
            return {**known, "duplicated": True}

        existing_codes = {str(row.get("隧道编码", "")).strip() for row in store.rows(MODULE)}
        seen_in_file: dict[str, int] = {}
        results: list[dict[str, Any]] = []
        accepted_values: list[dict[str, Any]] = []

        for line_no, cells in rows:
            problems: list[str] = []
            if len(cells) != len(IMPORT_COLUMNS):
                problems.append(f"列数为 {len(cells)}，应为 {len(IMPORT_COLUMNS)} 列（{'、'.join(IMPORT_COLUMNS)}）")
            values = dict(zip(IMPORT_COLUMNS, cells))
            code = str(values.get("隧道编码") or "").strip()
            for field in IMPORT_COLUMNS:
                if not str(values.get(field) or "").strip():
                    problems.append(f"{field}未填")
            length = str(values.get("隧道长度") or "").strip()
            if length and not _is_number(length):
                problems.append(f"隧道长度「{length}」不是数字")
            if code:
                if code in seen_in_file:
                    problems.append(f"隧道编码与本材料第 {seen_in_file[code]} 行重复")
                elif code in existing_codes:
                    problems.append(f"隧道编码「{code}」已存在于台账")
            if problems:
                results.append({"line": line_no, "code": code, "accepted": False, "reason": "；".join(problems)})
            else:
                seen_in_file[code] = line_no
                accepted_values.append(values)
                results.append({"line": line_no, "code": code, "accepted": True, "reason": "校验通过，已收入台账"})

        # 先算好全部新行再一次写入：要么整批合格行都进台账，要么一条不留。
        ledger = store.rows(MODULE)
        next_id = max((int(row.get("id", 0)) for row in ledger), default=0)
        self._batch_seq += 1
        batch_id = f"IMP-{self._batch_seq:04d}"
        new_entries: list[dict[str, Any]] = []
        for offset, values in enumerate(accepted_values, start=1):
            entry = {"id": next_id + offset}
            entry.update({field: values[field] for field in IMPORT_COLUMNS})
            entry["status"] = STATUS_ORDER[0]
            entry["pending"] = True
            entry["abnormal"] = False
            entry["import_batch"] = batch_id
            new_entries.append(entry)
        ledger.extend(new_entries)

        batch = {
            "batch_id": batch_id,
            "filename": filename or "",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "total": len(results),
            "accepted": len(accepted_values),
            "rejected": len(results) - len(accepted_values),
            "results": results,
        }
        self._imports[fingerprint] = batch
        return {**batch, "duplicated": False}

    def list_imports(self) -> list[dict[str, Any]]:
        """导入批次列表：每批附上台账侧的实际落库数，两处对得上才算一致。"""
        batches = []
        for batch in self._imports.values():
            batches.append({**self._reconcile(batch), "results": None})
        return sorted(batches, key=lambda item: str(item["batch_id"]), reverse=True)

    def get_import(self, batch_id: str) -> dict[str, Any] | None:
        for batch in self._imports.values():
            if batch["batch_id"] == batch_id:
                return self._reconcile(batch)
        return None

    def _reconcile(self, batch: dict[str, Any]) -> dict[str, Any]:
        ledger_count = sum(1 for row in store.rows(MODULE) if row.get("import_batch") == batch["batch_id"])
        return {
            **batch,
            "ledger_count": ledger_count,
            "matched": ledger_count == int(batch["accepted"]),
        }
