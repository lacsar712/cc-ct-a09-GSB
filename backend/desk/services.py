"""字头规则与刀补受理的唯一口径。

三条路径（页面预拦、直连接口、落库前刀号被改写）都必须过这里的规则，
退回文案只能取 PREFIX_REJECT_MESSAGE，保证口径一致。
"""

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from desk.models import OffsetSubmission, ToolPrefix

# 统一退回口径：任何引用方不得自行拼别的文案
PREFIX_REJECT_MESSAGE = "刀号必须以字头台已登记字头起笔，已退回"


def current_prefixes() -> list[str]:
    return list(ToolPrefix.objects.order_by("prefix").values_list("prefix", flat=True))


def match_prefix(tool_code: str, prefixes: list[str] | None = None) -> str:
    """返回命中的当前字头；未命中返回空串。长字头优先，避免长短字头互相遮蔽。"""
    if prefixes is None:
        prefixes = current_prefixes()
    code = tool_code or ""
    for p in sorted(prefixes, key=len, reverse=True):
        if p and code.startswith(p):
            return p
    return ""


def validate_tool_code(tool_code: str) -> str:
    """规则复核。收下返回归一化刀号；不合规抛 ValueError（文案即退回口径）。"""
    code = (tool_code or "").strip()
    if not code:
        raise ValueError("刀具编号不能为空")
    if not match_prefix(code):
        raise ValueError(PREFIX_REJECT_MESSAGE)
    return code


def accept_submission(*, tool_code: str, offset_um: int, user) -> OffsetSubmission:
    """提交落库的唯一入口。

    事务内：先按规则校验，再建行，随后以「实际落库行」的 tool_code 回读
    当前字头表复核——即使有人在落库前信号/触发器里把刀号改写成别的字头，
    这里也查得到并整体回滚，不会留下任何记录。
    """
    code = validate_tool_code(tool_code)
    with transaction.atomic():
        row = OffsetSubmission.objects.create(
            tool_code=code,
            offset_um=offset_um,
            submitted_by=user,
            status=OffsetSubmission.Status.PENDING,
        )
        row.refresh_from_db(fields=["tool_code"])
        try:
            validate_tool_code(row.tool_code)
        except ValueError:
            transaction.set_rollback(True)
            raise
    return row


def evaluate_verdict(offset_um: int) -> str:
    if abs(offset_um) <= settings.OFFSET_TOLERANCE_UM:
        return OffsetSubmission.Verdict.PASS
    return OffsetSubmission.Verdict.FAIL


def apply_verdict(submission: OffsetSubmission) -> None:
    submission.verdict = evaluate_verdict(submission.offset_um)
    submission.status = OffsetSubmission.Status.DONE
    submission.reviewed_at = timezone.now()
    submission.save(
        update_fields=["verdict", "status", "reviewed_at"],
    )
