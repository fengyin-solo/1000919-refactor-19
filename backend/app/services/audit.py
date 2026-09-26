"""内审检查业务规则：可执行动作与整改判断在这里统一计算。

列表、详情、动作提交三处都只能通过 :func:`evaluate_entry` 取结论，
避免同一条内审记录在不同入口算出不同的「下一步谁动、检查条款要不要重新核」。

判定口径（检查条款 + 整改期限 + 当前状态）：
- 待审核：审核员开始审核。
- 审核中：检查结果存在不符合项时，责任部门提交整改；否则审核员记录结果判通过。
- 待整改：整改期限已过（含到期日当天）后，审核员重新核查条款并记录复核结果；
  期限未满时不开放动作，由责任部门继续整改。
- 已通过：流程结束，无动作，不需要重新核查。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "audit"
REQUIRED_FIELDS = ["内审编号", "内审日期", "内审部门"]
STATUS_ORDER = ["待审核", "审核中", "已通过", "待整改"]

# 每个动作在统一口径下对应的目标状态。
ACTION_RULES = {"开始审核": "审核中", "记录结果": "已通过", "提交整改": "待整改"}
# 维持原口径：动作本身不改 abnormal 标记（种子数据里的异常量保持不变）。
NEGATIVE_ACTIONS = []

ACTION_START = "开始审核"
ACTION_RECORD = "记录结果"
ACTION_RECTIFY = "提交整改"

OWNER_AUDITOR = "审核员"
OWNER_OWNER_DEPT = "责任部门"

PASS_CONCLUSION = "内审通过，无需重新核查检查条款"


def _parse_day(value: Any) -> date | None:
    """把「整改期限」等日期字段解析成 date；解析不了就当作没有期限。"""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _has_nonconformity(entry: dict[str, Any]) -> bool:
    return bool(str(entry.get("不符合项") or "").strip())


def evaluate_entry(entry: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """内审可执行动作与整改判断的唯一实现。

    返回结论字典：available_actions / need_recheck / conclusion / next_owner，
    列表、详情与动作校验共用，任何入口都不得另写一套判断。
    """
    today = today or date.today()
    status = str(entry.get("status") or STATUS_ORDER[0])
    clause = str(entry.get("检查条款") or "").strip()
    deadline = _parse_day(entry.get("整改期限"))

    if status == "待审核":
        return {
            "available_actions": [ACTION_START],
            "need_recheck": False,
            "conclusion": "等待审核员开始审核，检查条款尚未核查",
            "next_owner": OWNER_AUDITOR,
        }

    if status == "审核中":
        if _has_nonconformity(entry):
            return {
                "available_actions": [ACTION_RECTIFY],
                "need_recheck": False,
                "conclusion": f"检查发现不符合项，由责任部门针对检查条款「{clause}」提交整改",
                "next_owner": OWNER_OWNER_DEPT,
            }
        return {
            "available_actions": [ACTION_RECORD],
            "need_recheck": False,
            "conclusion": "未发现不符合项，由审核员记录结果判通过",
            "next_owner": OWNER_AUDITOR,
        }

    if status == "待整改":
        overdue = deadline is not None and deadline <= today
        if overdue:
            target_clause = f"检查条款「{clause}」" if clause else "检查条款"
            return {
                "available_actions": [ACTION_RECORD],
                "need_recheck": True,
                "conclusion": f"整改期限已到，审核员需重新核查{target_clause}并记录复核结果",
                "next_owner": OWNER_AUDITOR,
            }
        return {
            "available_actions": [],
            "need_recheck": False,
            "conclusion": "责任部门整改中，整改期限未到，检查条款暂不重新核查",
            "next_owner": OWNER_OWNER_DEPT,
        }

    if status == "已通过":
        return {
            "available_actions": [],
            "need_recheck": False,
            "conclusion": PASS_CONCLUSION,
            "next_owner": None,
        }

    return {
        "available_actions": [],
        "need_recheck": False,
        "conclusion": f"未知内审状态「{status}」，暂无可执行动作",
        "next_owner": None,
    }


def serialize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """给列表/详情输出附加统一判定结论；原始字段一律原样保留。"""
    view = dict(entry)
    view.update(evaluate_entry(entry))
    return view


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
        return [serialize_entry(row) for row in page_rows], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return serialize_entry(entry)

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
        return serialize_entry(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"内审记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于内审检查可执行范围"

        # 是否允许执行，只认统一判定函数给出的结论，接口层不再另写状态判断。
        decision = evaluate_entry(entry)
        if action not in decision["available_actions"]:
            return None, (
                f"当前状态「{entry.get('status')}」下不能执行「{action}」：{decision['conclusion']}"
            )

        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        if action == ACTION_RECTIFY:
            entry.setdefault("整改记录", []).append(
                {
                    "动作": action,
                    "检查条款": entry.get("检查条款"),
                    "整改期限": entry.get("整改期限"),
                    "目标状态": target,
                }
            )

        entry["status"] = target
        # pending 沿用原口径（终态判定基于状态序列末位），避免概览统计走样。
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return serialize_entry(entry), f"内审记录已{action}"
