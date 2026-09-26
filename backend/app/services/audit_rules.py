"""内审可执行动作与整改判断的唯一实现。

内审列表、内审详情、提交整改三处都必须调用这里的函数，禁止各自再写一遍：
- ``evaluate_audit`` 按「检查条款 + 整改期限 + 不符合项」算出当前结论；
- ``available_actions`` 在结论之上给出当前允许执行的动作；
- ``submit_rectification`` 是提交整改动作的唯一入口，负责状态流转与历史留痕。

结论口径（同一内审编号在任何入口都一致）：
- 检查条款为空：条款未登记，不允许审核或整改；
- 检查条款需要重新核对（条款命中重新核对清单）：结论为「重新核对」，
  先核条款，整改材料不接收；
- 存在不符合项且整改期限已过：结论为「整改超期」，需重新核对条款后再整改；
- 存在不符合项且在整改期限内：结论为「待整改」，可提交整改；
- 无不符合项：结论为「符合」，审核可推进至通过。

注意：本模块只做判断与流转，不决定数据排列、分页，也不改历史展示字段。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# 结论与状态的统一词汇表
CONCLUSION_PENDING = "待审核"
CONCLUSION_REVIEWING = "审核中"
CONCLUSION_PASS = "符合"
CONCLUSION_RECTIFY = "待整改"
CONCLUSION_OVERDUE = "整改超期"
CONCLUSION_RECHECK = "重新核对"
CONCLUSION_MISSING = "条款未登记"

# 动作词汇表
ACTION_START = "开始审核"
ACTION_RECORD = "记录结果"
ACTION_SUBMIT = "提交整改"

# 状态（与既有 status 字段、历史数据保持一致）
STATUS_PENDING = "待审核"
STATUS_REVIEWING = "审核中"
STATUS_PASSED = "已通过"
STATUS_RECTIFYING = "待整改"

# 需要重新核对的检查条款关键字：命中即视为条款存疑，必须先核条款。
RECHECK_CLAUSE_KEYWORDS = ("待核", "待确认", "作废", "废止", "过期")

# 结论 -> 该结论下允许执行的动作
_CONCLUSION_ACTIONS: dict[str, list[str]] = {
    CONCLUSION_MISSING: [],
    CONCLUSION_RECHECK: [ACTION_RECORD],
    CONCLUSION_OVERDUE: [ACTION_RECORD],
    CONCLUSION_PENDING: [ACTION_START],
    CONCLUSION_REVIEWING: [ACTION_RECORD],
    CONCLUSION_RECTIFY: [ACTION_SUBMIT, ACTION_RECORD],
    CONCLUSION_PASS: [ACTION_RECORD],
}

_TERMINAL_STATUS = {STATUS_PASSED}


def _text(value: Any) -> str:
    return str(value or "").strip()


def parse_deadline(value: Any) -> date | None:
    """把整改期限解析成日期；解析不出来（空值/非日期文本）返回 None。"""
    raw = _text(value)
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def needs_recheck(clause: Any) -> bool:
    """检查条款是否需要重新核对：空条款单独走「未登记」，命中关键字走「重新核对」。"""
    text = _text(clause)
    if not text:
        return False
    return any(keyword in text for keyword in RECHECK_CLAUSE_KEYWORDS)


def has_nonconformity(entry: dict[str, Any]) -> bool:
    """是否存在不符合项。

    以「不符合项」字段为准；空字符串、无、/ 视为没有不符合。
    """
    value = _text(entry.get("不符合项"))
    if not value or value in {"无", "/", "—", "-"}:
        return False
    return True


def evaluate_audit(entry: dict[str, Any], *, today: date | None = None) -> str:
    """按检查条款与整改期限统一计算内审结论。列表/详情/整改三处都以此为准。

    已经办结（已通过）的记录维持「符合」，不因其历史上的不符合项或期限再被翻成超期，
    保证既有数据、历史整改记录的展示口径不走样。
    """
    today = today or date.today()

    if _text(entry.get("status")) == STATUS_PASSED:
        return CONCLUSION_PASS

    clause = _text(entry.get("检查条款"))
    if not clause:
        return CONCLUSION_MISSING
    if needs_recheck(clause):
        return CONCLUSION_RECHECK

    if has_nonconformity(entry):
        deadline = parse_deadline(entry.get("整改期限"))
        if deadline is not None and deadline < today:
            return CONCLUSION_OVERDUE
        return CONCLUSION_RECTIFY

    status = _text(entry.get("status"))
    if status == STATUS_PENDING:
        return CONCLUSION_PENDING
    return CONCLUSION_REVIEWING


def available_actions(entry: dict[str, Any], *, today: date | None = None) -> list[str]:
    """返回该内审记录当前可执行的动作；已通过的终态记录不再给出动作。"""
    if _text(entry.get("status")) in _TERMINAL_STATUS:
        return []
    return list(_CONCLUSION_ACTIONS.get(evaluate_audit(entry, today=today), []))


def _history(entry: dict[str, Any]) -> list[dict[str, Any]]:
    records = entry.setdefault("rectification_history", [])
    return records


def list_rectification_history(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """只读地返回历史整改记录，供详情展示；绝不改动顺序与内容。"""
    return [dict(item) for item in _history(entry)]


def submit_rectification(
    entry: dict[str, Any],
    values: dict[str, Any] | None = None,
    *,
    today: date | None = None,
) -> tuple[dict[str, Any] | None, str, bool]:
    """提交整改的唯一入口。

    返回 ``(entry, message, recheck_required)``：
    - 条款需重新核对 / 已超期 / 没有不符合项时拒绝接收，``entry`` 原样返回、
      ``recheck_required`` 标明是否必须先重新核对检查条款；
    - 接收后状态置为「已通过」并追加一条不可变的整改历史。
    """
    today = today or date.today()
    values = values or {}
    conclusion = evaluate_audit(entry, today=today)

    if conclusion == CONCLUSION_MISSING:
        return None, "检查条款未登记，无法提交整改，请先补全检查条款", False
    if conclusion == CONCLUSION_RECHECK:
        return None, "检查条款需要重新核对，核对完成前暂不接收整改材料", True
    if conclusion == CONCLUSION_OVERDUE:
        return None, "整改期限已过，请先重新核对检查条款并确认整改期限，再提交整改", True
    if conclusion == CONCLUSION_PASS:
        return None, "该记录已通过，无需重复提交整改", False
    if conclusion != CONCLUSION_RECTIFY:
        return None, f"当前结论为「{conclusion}」，暂不能提交整改", False

    note = _text(values.get("整改说明") or values.get("note")) or "现场整改完成"
    _history(entry).append({
        "日期": today.isoformat(),
        "检查条款": _text(entry.get("检查条款")),
        "不符合项": _text(entry.get("不符合项")),
        "整改期限": _text(entry.get("整改期限")),
        "整改说明": note,
    })
    entry["status"] = STATUS_PASSED
    entry["pending"] = False
    entry["abnormal"] = False
    return entry, "整改已提交，内审记录转为已通过", False
