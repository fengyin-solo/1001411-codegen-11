"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ImportRowResult(BaseModel):
    """台账导入的单行结论：收下还是被拒，被拒时写明原因。"""

    row_no: int
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    values: dict[str, Any] = Field(default_factory=dict)
    entry_id: int | None = None


class ImportBatchResult(BaseModel):
    """一份台账材料的导入结果：批次摘要加逐行结论，重复编码单独列出。"""

    ok: bool
    batch_id: str
    filename: str
    imported_at: str
    deduplicated: bool = False
    total: int = 0
    accepted: int = 0
    rejected: int = 0
    duplicate_codes: list[str] = Field(default_factory=list)
    rows: list[ImportRowResult] = Field(default_factory=list)
    message: str = ""



class RoadEntry(BaseModel):
    """道路设施明细结构。"""

    field_0: str | None = None  # 设施编码
    field_1: str | None = None  # 道路名称
    field_2: str | None = None  # 道路等级
    field_3: str | None = None  # 起止桩号
    field_4: str | None = None  # 路面结构
    field_5: str | None = None  # 管养单位
    field_6: str | None = None  # 建成年份
    field_7: str | None = None  # 设施状态

class BridgeEntry(BaseModel):
    """桥梁设施明细结构。"""

    field_0: str | None = None  # 桥梁编码
    field_1: str | None = None  # 桥梁名称
    field_2: str | None = None  # 桥梁类型
    field_3: str | None = None  # 跨越对象
    field_4: str | None = None  # 桥梁全长
    field_5: str | None = None  # 设计荷载
    field_6: str | None = None  # 建成年份
    field_7: str | None = None  # 桥梁状态

class TunnelEntry(BaseModel):
    """隧道设施明细结构。"""

    field_0: str | None = None  # 隧道编码
    field_1: str | None = None  # 隧道名称
    field_2: str | None = None  # 隧道长度
    field_3: str | None = None  # 断面形式
    field_4: str | None = None  # 照明方式
    field_5: str | None = None  # 通风方式
    field_6: str | None = None  # 管养单位
    field_7: str | None = None  # 隧道状态

class PatrolEntry(BaseModel):
    """巡查单明细结构。"""

    field_0: str | None = None  # 巡查单号
    field_1: str | None = None  # 巡查路线
    field_2: str | None = None  # 巡查人员
    field_3: str | None = None  # 巡查日期
    field_4: str | None = None  # 巡查里程
    field_5: str | None = None  # 发现问题数
    field_6: str | None = None  # 巡查时长
    field_7: str | None = None  # 巡查状态

class DiseaseEntry(BaseModel):
    """病害记录明细结构。"""

    field_0: str | None = None  # 病害编号
    field_1: str | None = None  # 所在设施
    field_2: str | None = None  # 病害类型
    field_3: str | None = None  # 病害位置
    field_4: str | None = None  # 严重等级
    field_5: str | None = None  # 发现日期
    field_6: str | None = None  # 登记人员
    field_7: str | None = None  # 病害状态

class AssessEntry(BaseModel):
    """评定记录明细结构。"""

    field_0: str | None = None  # 评定编号
    field_1: str | None = None  # 评定对象
    field_2: str | None = None  # 评定周期
    field_3: str | None = None  # 技术等级
    field_4: str | None = None  # 评定结论
    field_5: str | None = None  # 评定人员
    field_6: str | None = None  # 评定日期
    field_7: str | None = None  # 评定状态

class PlanEntry(BaseModel):
    """养护计划明细结构。"""

    field_0: str | None = None  # 计划编号
    field_1: str | None = None  # 养护类型
    field_2: str | None = None  # 养护对象
    field_3: str | None = None  # 计划工期
    field_4: str | None = None  # 预算金额
    field_5: str | None = None  # 编制人员
    field_6: str | None = None  # 审批人员
    field_7: str | None = None  # 计划状态

class WorkEntry(BaseModel):
    """施工任务明细结构。"""

    field_0: str | None = None  # 施工编号
    field_1: str | None = None  # 关联计划
    field_2: str | None = None  # 承接单位
    field_3: str | None = None  # 开工日期
    field_4: str | None = None  # 完工日期
    field_5: str | None = None  # 完成工程量
    field_6: str | None = None  # 监理人员
    field_7: str | None = None  # 施工状态

class AcceptEntry(BaseModel):
    """验收单明细结构。"""

    field_0: str | None = None  # 验收单号
    field_1: str | None = None  # 关联施工
    field_2: str | None = None  # 验收项目
    field_3: str | None = None  # 验收标准
    field_4: str | None = None  # 验收结论
    field_5: str | None = None  # 验收人员
    field_6: str | None = None  # 验收日期
    field_7: str | None = None  # 验收状态

class PotholeEntry(BaseModel):
    """修补单明细结构。"""

    field_0: str | None = None  # 修补单号
    field_1: str | None = None  # 所在路段
    field_2: str | None = None  # 修补面积
    field_3: str | None = None  # 修补材料
    field_4: str | None = None  # 用料数量
    field_5: str | None = None  # 作业班组
    field_6: str | None = None  # 完成日期
    field_7: str | None = None  # 修补状态

class CrackEntry(BaseModel):
    """处置单明细结构。"""

    field_0: str | None = None  # 处置单号
    field_1: str | None = None  # 所在路段
    field_2: str | None = None  # 裂缝类型
    field_3: str | None = None  # 裂缝长度
    field_4: str | None = None  # 灌缝材料
    field_5: str | None = None  # 作业班组
    field_6: str | None = None  # 完成日期
    field_7: str | None = None  # 处置状态

class DrainEntry(BaseModel):
    """排水设施明细结构。"""

    field_0: str | None = None  # 设施编号
    field_1: str | None = None  # 设施类型
    field_2: str | None = None  # 所在道路
    field_3: str | None = None  # 检查井数量
    field_4: str | None = None  # 上次清疏日
    field_5: str | None = None  # 下次清疏日
    field_6: str | None = None  # 责任班组
    field_7: str | None = None  # 设施状态

class LightEntry(BaseModel):
    """照明设施明细结构。"""

    field_0: str | None = None  # 设施编号
    field_1: str | None = None  # 灯杆编号
    field_2: str | None = None  # 灯具类型
    field_3: str | None = None  # 所在道路
    field_4: str | None = None  # 亮灯率
    field_5: str | None = None  # 上次检修日
    field_6: str | None = None  # 责任班组
    field_7: str | None = None  # 设施状态

class MaterialEntry(BaseModel):
    """养护材料明细结构。"""

    field_0: str | None = None  # 材料编号
    field_1: str | None = None  # 材料名称
    field_2: str | None = None  # 规格型号
    field_3: str | None = None  # 结存数量
    field_4: str | None = None  # 计量单位
    field_5: str | None = None  # 存放场地
    field_6: str | None = None  # 保管人员
    field_7: str | None = None  # 材料状态

class EquipEntry(BaseModel):
    """养护机械明细结构。"""

    field_0: str | None = None  # 机械编号
    field_1: str | None = None  # 机械名称
    field_2: str | None = None  # 机械型号
    field_3: str | None = None  # 停放场地
    field_4: str | None = None  # 上次保养日
    field_5: str | None = None  # 下次保养日
    field_6: str | None = None  # 责任人
    field_7: str | None = None  # 机械状态

class FundEntry(BaseModel):
    """资金记录明细结构。"""

    field_0: str | None = None  # 资金编号
    field_1: str | None = None  # 费用类别
    field_2: str | None = None  # 项目名称
    field_3: str | None = None  # 批复金额
    field_4: str | None = None  # 已用金额
    field_5: str | None = None  # 剩余额度
    field_6: str | None = None  # 审批人员
    field_7: str | None = None  # 资金状态

class ComplaintEntry(BaseModel):
    """诉求记录明细结构。"""

    field_0: str | None = None  # 诉求编号
    field_1: str | None = None  # 诉求来源
    field_2: str | None = None  # 诉求内容
    field_3: str | None = None  # 涉及设施
    field_4: str | None = None  # 受理人员
    field_5: str | None = None  # 处理措施
    field_6: str | None = None  # 办理期限
    field_7: str | None = None  # 诉求状态

class ArchiveEntry(BaseModel):
    """档案记录明细结构。"""

    field_0: str | None = None  # 档案编号
    field_1: str | None = None  # 关联设施
    field_2: str | None = None  # 档案类型
    field_3: str | None = None  # 资料名称
    field_4: str | None = None  # 存放位置
    field_5: str | None = None  # 归档人员
    field_6: str | None = None  # 归档日期
    field_7: str | None = None  # 档案状态
