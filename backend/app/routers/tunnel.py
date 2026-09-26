"""隧道设施接口：维护隧道设施，覆盖办理移交、安排检修、停用隧道等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, ImportPayload, PageResult
from app.services.tunnel import TunnelService

router = APIRouter(prefix="/api/tunnel", tags=["隧道设施"])

service = TunnelService()

LIST_FIELDS = ["隧道编码", "隧道名称", "隧道长度", "断面形式", "照明方式", "通风方式", "管养单位", "隧道状态"]
STATUSES = ["待移交", "正常养护", "检修封闭", "已停用"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按隧道编码检索"),
    status: str | None = Query(default=None, description="待移交、正常养护、检修封闭、已停用"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按隧道编码与状态过滤隧道设施列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出隧道设施清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "tunnel", "total": total, "items": items}


@router.post("/import")
def import_entries(payload: ImportPayload) -> dict[str, Any]:
    """导入一份台账材料：逐行校验落库并返回每行结果；同一份材料重复提交只算第一次。"""
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="材料内容为空，请按固定列整理后再上传")
    return service.import_entries(content=payload.content, filename=payload.filename)


@router.get("/imports")
def list_imports() -> dict[str, Any]:
    """导入批次列表：每批附台账侧落库数，结果列表与隧道台账对账用。"""
    return {"items": service.list_imports()}


@router.get("/imports/{batch_id}")
def get_import(batch_id: str) -> dict[str, Any]:
    """单个批次的逐行结果；批次不存在时给出可读的错误说明。"""
    batch = service.get_import(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"导入批次 {batch_id} 不存在")
    return batch


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条隧道设施明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"隧道设施 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条隧道设施，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="隧道设施已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条隧道设施执行办理移交、安排检修、停用隧道；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
