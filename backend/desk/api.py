from datetime import datetime
from typing import Optional

from django.db import transaction
from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import OffsetSubmission, PrefixHistory, ToolPrefix, User
from desk.services import PREFIX_REJECT_MESSAGE, accept_submission

api = NinjaAPI(title="数控刀补复核台", version="1.1")


class HealthOut(Schema):
    status: str


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    token: str
    username: str
    role: str
    can_write: bool


class SubmissionIn(Schema):
    tool_code: str
    offset_um: int


class SubmissionOut(Schema):
    id: int
    tool_code: str
    offset_um: int
    status: str
    verdict: str
    created_at: datetime
    reviewed_at: Optional[datetime]


class PrefixIn(Schema):
    prefix: str


class PrefixOut(Schema):
    prefix: str
    created_at: datetime


class PrefixHistoryOut(Schema):
    id: int
    prefix: str
    action: str
    action_label: str
    operator: Optional[str]
    created_at: datetime


class RuleOut(Schema):
    reject_message: str
    prefixes: list[str]


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        tool_code=row.tool_code,
        offset_um=row.offset_um,
        status=row.status,
        verdict=row.verdict or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def _require_writer(user: User) -> None:
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能维护字头或提交刀补")


def _history_to_out(row: PrefixHistory) -> PrefixHistoryOut:
    return PrefixHistoryOut(
        id=row.id,
        prefix=row.prefix,
        action=row.action,
        action_label=row.get_action_display(),
        operator=row.operator.username if row.operator else None,
        created_at=row.created_at,
    )


@api.get("/health", response=HealthOut)
def health(request: HttpRequest):
    return {"status": "ok"}


@api.post("/auth/login", response=LoginOut)
def login(request: HttpRequest, body: LoginIn):
    try:
        user = User.objects.get(username=body.username)
    except User.DoesNotExist:
        raise HttpError(401, "用户名或密码错误")
    if not verify_password(body.password, user.password):
        raise HttpError(401, "用户名或密码错误")
    token = create_access_token(user)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "can_write": user.can_write,
    }


@api.get("/submissions", response=list[SubmissionOut], auth=bearer_auth)
def list_submissions(request: HttpRequest):
    rows = OffsetSubmission.objects.all()[:200]
    return [_to_out(r) for r in rows]


@api.get("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def get_submission(request: HttpRequest, submission_id: int):
    try:
        row = OffsetSubmission.objects.get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    return _to_out(row)


@api.post("/submissions", response=SubmissionOut, auth=bearer_auth)
def create_submission(request: HttpRequest, body: SubmissionIn):
    user: User = request.auth
    _require_writer(user)
    try:
        row = accept_submission(
            tool_code=body.tool_code,
            offset_um=body.offset_um,
            user=user,
        )
    except ValueError as exc:
        # ValueError 的文案即统一退回口径（页面/直连/落库前改写三条路径一致）
        raise HttpError(400, str(exc))
    return _to_out(row)


@api.get("/prefixes/rule", response=RuleOut, auth=bearer_auth)
def get_prefix_rule(request: HttpRequest):
    """供页面预拦取当前字头与统一退回文案，页面不得自创口径。"""
    return {
        "reject_message": PREFIX_REJECT_MESSAGE,
        "prefixes": list(
            ToolPrefix.objects.order_by("prefix").values_list("prefix", flat=True)
        ),
    }


@api.get("/prefixes", response=list[PrefixOut], auth=bearer_auth)
def list_prefixes(request: HttpRequest):
    rows = ToolPrefix.objects.order_by("prefix")
    return [PrefixOut(prefix=r.prefix, created_at=r.created_at) for r in rows]


# 静态路径必须在 /prefixes/{prefix} 参数化路由之前注册，否则会被抢占成 405
@api.get("/prefixes/history", response=list[PrefixHistoryOut], auth=bearer_auth)
def list_prefix_history(request: HttpRequest):
    rows = PrefixHistory.objects.select_related("operator").all()[:200]
    return [_history_to_out(r) for r in rows]


@api.post("/prefixes", response=PrefixOut, auth=bearer_auth)
def add_prefix(request: HttpRequest, body: PrefixIn):
    user: User = request.auth
    _require_writer(user)
    prefix = (body.prefix or "").strip()
    if not prefix:
        raise HttpError(400, "字头不能为空")
    if len(prefix) > 16:
        raise HttpError(400, "字头最长 16 个字符")
    with transaction.atomic():
        row, created = ToolPrefix.objects.get_or_create(
            prefix=prefix,
            defaults={"created_by": user},
        )
        if not created:
            raise HttpError(409, "字头已登记，无需重复登记")
        PrefixHistory.objects.create(
            prefix=prefix,
            action=PrefixHistory.Action.ADD,
            operator=user,
        )
    return PrefixOut(prefix=row.prefix, created_at=row.created_at)


@api.delete("/prefixes/{prefix}", auth=bearer_auth)
def remove_prefix(request: HttpRequest, prefix: str):
    user: User = request.auth
    _require_writer(user)
    target = prefix.strip()
    with transaction.atomic():
        try:
            row = ToolPrefix.objects.select_for_update().get(prefix=target)
        except ToolPrefix.DoesNotExist:
            raise HttpError(404, "字头不存在或已删除")
        row.delete()
        PrefixHistory.objects.create(
            prefix=target,
            action=PrefixHistory.Action.REMOVE,
            operator=user,
        )
    return {"status": "deleted", "prefix": target}
