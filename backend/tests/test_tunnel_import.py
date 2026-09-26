"""隧道台账导入的验收测试：逐行校验、幂等、原子重做与结果台账一致性。"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.tunnel import TunnelService
from app.store import store

client = TestClient(app)

HEADER = "隧道编码,隧道名称,隧道长度,断面形式,照明通风方式"


def upload(content: bytes, filename: str = "隧道台账.csv"):
    return client.post("/api/tunnel/import", files={"file": (filename, content, "text/csv")})


def ledger_rows() -> list[dict]:
    response = client.get("/api/tunnel", params={"size": 200})
    assert response.status_code == 200
    return response.json()["items"]


def test_import_partial_success_and_row_reasons():
    material = "\n".join([
        HEADER,
        "IMP-A-001,青云隧道,1200,分离式,LED照明/机械通风",
        "IMP-A-002,,800,单洞,自然通风",
        "IMP-A-003,白谷隧道,abc,分离式,LED照明",
        "IMP-A-001,重复编码行,900,单洞,自然通风",
        "TUNN-0001,撞台账编码,600,单洞,自然通风",
        "IMP-A-004,长深隧道,2350.5,连拱式,LED照明、机械通风",
    ]).encode("utf-8")

    response = upload(material)
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == 6
    assert result["accepted"] == 2
    assert result["rejected"] == 4
    assert result["deduplicated"] is False

    rows = {row["row_no"]: row for row in result["rows"]}
    assert rows[1]["accepted"] is True
    assert rows[2]["accepted"] is False and any("必填字段未填" in r and "隧道名称" in r for r in rows[2]["reasons"])
    assert rows[3]["accepted"] is False and any("不是数字" in r for r in rows[3]["reasons"])
    assert rows[4]["accepted"] is False and any("第 1 行重复" in r for r in rows[4]["reasons"])
    assert rows[5]["accepted"] is False and any("台账已有记录重复" in r for r in rows[5]["reasons"])
    assert rows[6]["accepted"] is True

    # 重复编码单独点出来：材料内重复与撞台账的都列上
    assert result["duplicate_codes"] == ["IMP-A-001", "TUNN-0001"]

    # 被拒的行不进台账，收下的行按批次号能查到
    codes = {row["隧道编码"] for row in ledger_rows()}
    assert {"IMP-A-001", "IMP-A-004"} <= codes
    assert "IMP-A-002" not in codes and "IMP-A-003" not in codes
    batch_id = result["batch_id"]
    imported = [row for row in ledger_rows() if row.get("来源批次") == batch_id]
    assert len(imported) == 2
    first = next(row for row in imported if row["隧道编码"] == "IMP-A-001")
    assert first["隧道长度"] == 1200
    assert first["照明方式"] == "LED照明" and first["通风方式"] == "机械通风"
    assert first["status"] == "待移交"


def test_same_material_counts_once():
    material = "\n".join([
        HEADER,
        "IMP-B-001,雾岭隧道,860,单洞,LED照明/机械通风",
        "IMP-B-002,松坪隧道,1340,分离式,自然通风",
    ]).encode("utf-8")

    first = upload(material).json()
    before = len(ledger_rows())
    second = upload(material).json()
    after = len(ledger_rows())

    assert second["deduplicated"] is True
    assert second["batch_id"] == first["batch_id"]
    assert "未重复入账" in second["message"]
    assert before == after  # 重复交上来只算一次，台账不再加行

    batches = client.get("/api/tunnel/imports").json()["items"]
    assert sum(1 for b in batches if b["batch_id"] == first["batch_id"]) == 1


def test_all_rows_rejected_still_records_batch_and_ledgers_untouched():
    material = "\n".join([
        HEADER,
        "IMP-C-001,,一百,单洞,自然通风",
        "TUNN-0002,撞台账,500,单洞,自然通风",
    ]).encode("utf-8")

    before = len(ledger_rows())
    result = upload(material).json()
    assert result["accepted"] == 0 and result["rejected"] == 2
    assert len(ledger_rows()) == before  # 一行不合格不拖累其余行，全拒时台账一行不多

    again = upload(material).json()
    assert again["deduplicated"] is True
    assert len(ledger_rows()) == before


def test_result_list_matches_ledger():
    material = "\n".join([
        HEADER,
        "IMP-D-001,青杠隧道,720,单洞,LED照明/机械通风",
        "IMP-D-002,断渠隧道,not-a-number,单洞,自然通风",
        "IMP-D-003,梨树隧道,1980,分离式,LED照明/机械通风",
    ]).encode("utf-8")
    result = upload(material).json()
    batch_id = result["batch_id"]

    detail = client.get(f"/api/tunnel/imports/{batch_id}")
    assert detail.status_code == 200
    accepted = [row for row in detail.json()["rows"] if row["accepted"]]
    imported = [row for row in ledger_rows() if row.get("来源批次") == batch_id]

    # 结果列表里收下的行与台账里该批次的行一一对应
    assert len(accepted) == len(imported) == 2
    assert {row["values"]["隧道编码"] for row in accepted} == {row["隧道编码"] for row in imported}
    assert {row["entry_id"] for row in accepted} == {row["id"] for row in imported}

    missing = client.get("/api/tunnel/imports/IMP-9999")
    assert missing.status_code == 404


def test_split_lighting_ventilation_columns_also_accepted():
    material = "\n".join([
        "隧道编码,隧道名称,隧道长度,断面形式,照明方式,通风方式",
        "IMP-E-001,石垭隧道,640,单洞,LED照明,机械通风",
    ]).encode("utf-8")
    result = upload(material).json()
    assert result["accepted"] == 1
    entry = next(row for row in ledger_rows() if row["隧道编码"] == "IMP-E-001")
    assert entry["照明方式"] == "LED照明" and entry["通风方式"] == "机械通风"


def test_gbk_encoded_material_accepted():
    material = "\n".join([
        HEADER,
        "IMP-F-001,青龙背隧道,930,单洞,LED照明/机械通风",
    ]).encode("gb18030")
    result = upload(material).json()
    assert result["accepted"] == 1
    assert any(row["隧道编码"] == "IMP-F-001" for row in ledger_rows())


def test_bad_material_rejected_with_readable_message():
    missing_column = "隧道编码,隧道名称,隧道长度,照明通风方式\nIMP-G-001,青云,100,LED照明\n".encode("utf-8")
    response = upload(missing_column)
    assert response.status_code == 400
    assert "断面形式" in response.json()["detail"]

    empty = upload(b"")
    assert empty.status_code == 400

    no_lighting = "隧道编码,隧道名称,隧道长度,断面形式\nIMP-G-002,青云,100,单洞\n".encode("utf-8")
    response = upload(no_lighting)
    assert response.status_code == 400
    assert "照明通风" in response.json()["detail"]


def test_interrupted_import_redoes_whole_batch_without_partial_rows(monkeypatch):
    service = TunnelService()
    material = "\n".join([
        HEADER,
        "IMP-R-001,回龙湾隧道,1100,单洞,LED照明/机械通风",
        "IMP-R-002,庙梁隧道,1250,分离式,LED照明/机械通风",
    ]).encode("utf-8")

    class Boom(list):
        def extend(self, items):  # 模拟入账中途断电
            raise RuntimeError("模拟导入中断")

    real_rows = store.rows
    monkeypatch.setattr(store, "rows", lambda module: Boom() if module == "tunnel" else real_rows(module))
    before = len(real_rows("tunnel"))
    with pytest.raises(RuntimeError):
        service.import_ledger(filename="重做.csv", content=material)
    monkeypatch.undo()

    assert len(real_rows("tunnel")) == before  # 不留半条残行

    redone = service.import_ledger(filename="重做.csv", content=material)
    assert redone["accepted"] == 2  # 整批重做，全部收下
    assert len(real_rows("tunnel")) == before + 2


def test_existing_closure_flow_intact():
    response = client.post("/api/tunnel/2/actions", json={"values": {"action": "安排检修"}})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["entry"]["status"] == "检修封闭"

    bad = client.post("/api/tunnel/2/actions", json={"values": {"action": "直接删除"}})
    assert bad.json()["ok"] is False

    missing = client.get("/api/tunnel/99999")
    assert missing.status_code == 404


def test_export_route_not_shadowed():
    response = client.get("/api/tunnel/export")
    assert response.status_code == 200
    assert response.json()["module"] == "tunnel"
