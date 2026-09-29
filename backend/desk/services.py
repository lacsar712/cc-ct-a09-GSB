"""业务规则收口处。

刀号字头规则只在本模块判定：页面、绕过页面的直连接口、以及落库前的写入
都必须经过 ``accept_submission``，三处退回口径一致。已收下的旧刀号在字头
被删后原样保留（``OffsetSubmission.prefix`` 为字符串快照，不与字头表建外键）。
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from desk.models import (
    OffsetSubmission,
    PrefixChangeLog,
    RejectedToolCode,
    ToolPrefix,
)


class InvalidToolCode(ValueError):
    """刀号不合字头规则，退回。message 即三路径统一口径。"""

    def __init__(self, message: str, tool_code: str = "", prefix: str = ""):
        super().__init__(message)
        self.tool_code = tool_code
        self.prefix = prefix


class PrefixAlreadyExists(ValueError):
    pass


class PrefixMissing(ValueError):
    pass


def reject_message(tool_code: str, head: str) -> str:
    """网页预拦与后端退回共用的统一口径。"""
    return (
        f"刀号「{tool_code}」起笔字头「{head}」未在字头台登记，"
        f"刀号必须以已登记字头起笔，退回。"
    )


def registered_prefixes() -> list[str]:
    return list(ToolPrefix.objects.order_by("-prefix").values_list("prefix", flat=True))


def match_prefix(tool_code: str) -> str | None:
    """按最长字头匹配起笔；未登记任何字头或不起笔于登记字头时返回 None。"""
    matched: str | None = None
    for prefix in registered_prefixes():
        if tool_code.startswith(prefix):
            if matched is None or len(prefix) > len(matched):
                matched = prefix
    return matched


def guess_head(tool_code: str) -> str:
    """无匹配时用于提示与样例的起笔字头（首字符）。"""
    return tool_code[:1]


def accept_submission(*, user, tool_code: str, offset_um: int) -> OffsetSubmission:
    """落库前的唯一收口：先判字头再创建，中间不得改写刀号。

    不合字头：记一条退回样例并抛 InvalidToolCode，不产生任何刀补记录。
    """
    code = (tool_code or "").strip()
    if not code:
        raise InvalidToolCode("刀具编号不能为空")

    matched = match_prefix(code)
    if matched is None:
        head = guess_head(code)
        reason = reject_message(code, head)
        RejectedToolCode.objects.create(
            tool_code=code,
            prefix=head,
            offset_um=offset_um,
            reason=reason,
            submitted_by=user,
            submitter_name=user.username if user is not None else "",
        )
        raise InvalidToolCode(reason, tool_code=code, prefix=head)

    return OffsetSubmission.objects.create(
        tool_code=code,
        prefix=matched,
        offset_um=offset_um,
        submitted_by=user,
        status=OffsetSubmission.Status.PENDING,
    )


def add_prefix(operator, raw: str) -> ToolPrefix:
    prefix = (raw or "").strip()
    if not prefix:
        raise InvalidToolCode("字头不能为空")
    try:
        with transaction.atomic():
            obj = ToolPrefix.objects.create(prefix=prefix, created_by=operator)
            PrefixChangeLog.objects.create(
                prefix=prefix,
                action=PrefixChangeLog.Action.ADD,
                operator=operator,
                operator_name=operator.username if operator is not None else "",
            )
    except IntegrityError:
        raise PrefixAlreadyExists(prefix)
    return obj


def remove_prefix(operator, raw: str) -> str:
    """删字头只动字头表并写履历；已收下的旧刀号一字不改。"""
    prefix = (raw or "").strip()
    if not prefix:
        raise InvalidToolCode("字头不能为空")
    with transaction.atomic():
        deleted, _ = (
            ToolPrefix.objects.select_for_update()
            .filter(prefix=prefix)
            .delete()
        )
        if not deleted:
            raise PrefixMissing(prefix)
        PrefixChangeLog.objects.create(
            prefix=prefix,
            action=PrefixChangeLog.Action.REMOVE,
            operator=operator,
            operator_name=operator.username if operator is not None else "",
        )
    return prefix


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
