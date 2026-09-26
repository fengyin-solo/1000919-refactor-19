"""内审检查业务规则。

列表组装、详情读取、动作（开始审核 / 记录结果 / 提交整改）全部调用
``app.services.audit_rules`` 里的唯一判断实现，本层只负责筛选、分页与存取，
不再各自维护一套动作与整改口径。
"""
from __future__ import annotations

from typing import Any

from app.store import store
from app.services import audit_rules as rules

MODULE = "audit"
REQUIRED_FIELDS = ["内审编号", "内审日期", "内审部门"]

# 记录结果时允许随动作更新的业务字段（用于重新核对条款 / 补登不符合项与整改期限）
RECORD_FIELDS = ["检查条款", "检查结果", "不符合项", "整改期限"]


class AuditService:
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
            rows = [row for row in rows if keyword in str(row.get("内审编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        # 结论与可执行动作随列表带出，但只在副本上附加，不落库、不改既有字段
        return [self._with_judgement(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        detail = self._with_judgement(entry)
        # 详情额外只读带出历史整改记录，顺序与内容保持入库时原样
        detail["rectification_history"] = rules.list_rectification_history(entry)
        return detail

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = rules.STATUS_PENDING
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"内审记录 {entry_id} 不存在或已归档"

        if action == rules.ACTION_SUBMIT:
            updated, message, _recheck = rules.submit_rectification(entry, values)
            if updated is None or updated.get("status") != rules.STATUS_PASSED:
                return None, message
            return updated, message

        if action == rules.ACTION_START:
            return self._start_review(entry)

        if action == rules.ACTION_RECORD:
            return self._record_result(entry, values or {})

        return None, f"动作「{action}」不属于内审检查可执行范围"

    # ---- 以下为内部流转，动作是否允许仍统一问 rules.available_actions ----

    def _start_review(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if rules.ACTION_START not in rules.available_actions(entry):
            return None, f"当前结论为「{rules.evaluate_audit(entry)}」，不能开始审核"
        entry["status"] = rules.STATUS_REVIEWING
        entry["pending"] = True
        return entry, "内审记录已开始审核"

    def _record_result(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if rules.ACTION_RECORD not in rules.available_actions(entry):
            return None, f"当前结论为「{rules.evaluate_audit(entry)}」，不能记录结果"

        for field in RECORD_FIELDS:
            if field in values and str(values.get(field) or "").strip():
                entry[field] = values[field]

        conclusion = rules.evaluate_audit(entry)
        if conclusion == rules.CONCLUSION_MISSING:
            return None, "检查条款未登记，请补全检查条款后再记录结果"
        if conclusion == rules.CONCLUSION_RECHECK:
            return None, "检查条款需要重新核对，核对完成前不能记录结论"
        if conclusion == rules.CONCLUSION_OVERDUE:
            return None, "整改期限已过，请重新核对检查条款并确认整改期限后再记录"

        if conclusion == rules.CONCLUSION_RECTIFY:
            entry["status"] = rules.STATUS_RECTIFYING
            entry["pending"] = True
            entry["abnormal"] = True
            return entry, "检查结果已记录，存在不符合项，进入待整改"

        entry["status"] = rules.STATUS_PASSED
        entry["pending"] = False
        entry["abnormal"] = False
        return entry, "检查结果已记录，内审结论为符合"

    @staticmethod
    def _with_judgement(entry: dict[str, Any]) -> dict[str, Any]:
        view = dict(entry)
        view["conclusion"] = rules.evaluate_audit(entry)
        view["available_actions"] = rules.available_actions(entry)
        return view
