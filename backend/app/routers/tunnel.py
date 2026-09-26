"""隧道设施接口：维护隧道设施，覆盖办理移交、安排检修、停用隧道等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.schemas import ActionResult, EntryPayload, ImportBatchResult, PageResult
from app.services.tunnel import IMPORT_TEMPLATE_COLUMNS, TunnelService

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


@router.post("/import", response_model=ImportBatchResult)
def import_entries(file: UploadFile = File(..., description="固定列的隧道台账材料（CSV）")) -> ImportBatchResult:
    """上传固定列台账材料并导入隧道台账。

    固定列：隧道编码、隧道名称、隧道长度、断面形式、照明通风方式（或拆成照明方式、通风方式两列）。
    逐行校验编码重复、长度非数字、必填未填，每行各自收下或被拒，互不影响；
    同一份材料重复上传只入账一次；中断后整批重交不会留下半条残行。
    """
    try:
        result = service.import_ledger(filename=file.filename or "未命名材料", content=file.file.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportBatchResult(**result)


@router.get("/imports", response_model=PageResult[dict])
def list_import_batches() -> PageResult[dict]:
    """列出全部台账导入批次的摘要，最新一批排最前。"""
    items = service.list_import_batches()
    return PageResult(items=items, total=len(items), page=1, size=len(items) or 1)


@router.get("/imports/{batch_id}", response_model=ImportBatchResult)
def get_import_batch(batch_id: str) -> ImportBatchResult:
    """读取某一批导入的逐行结果；批次号不存在时给出可读的错误说明。"""
    batch = service.get_import_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"导入批次 {batch_id} 不存在")
    return ImportBatchResult(**batch)


@router.get("/import-template")
def import_template() -> dict[str, Any]:
    """给出导入材料的固定列与一行示例，方便照着整理台账材料。"""
    example = ["TUNN-0101", "云峰山隧道", "1520", "分离式", "LED照明/机械通风"]
    return {"module": "tunnel", "columns": IMPORT_TEMPLATE_COLUMNS, "example": example}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出隧道设施清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "tunnel", "total": total, "items": items}


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
