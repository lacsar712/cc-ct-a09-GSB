from datetime import datetime
from typing import Optional

from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import (
    OffsetSubmission,
    PrefixChangeLog,
    RejectedToolCode,
    ToolPrefix,
    User,
)
from desk.services import (
    InvalidToolCode,
    PrefixAlreadyExists,
    PrefixMissing,
    accept_submission,
    add_prefix,
    remove_prefix,
)

api = NinjaAPI(title="数控刀补复核台", version="1.0")


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
    prefix: str
    offset_um: int
    status: str
    verdict: str
    created_at: datetime
    reviewed_at: Optional[datetime]


class PrefixIn(Schema):
    prefix: str


class PrefixOut(Schema):
    id: int
    prefix: str
    created_by: Optional[str]
    created_at: datetime


class PrefixChangeLogOut(Schema):
    id: int
    prefix: str
    action: str
    action_label: str
    operator_name: str
    created_at: datetime


class RejectedOut(Schema):
    id: int
    tool_code: str
    prefix: str
    offset_um: Optional[int]
    reason: str
    submitter_name: str
    created_at: datetime


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        tool_code=row.tool_code,
        prefix=row.prefix,
        offset_um=row.offset_um,
        status=row.status,
        verdict=row.verdict or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


def _require_writer(user: User) -> None:
    if not user.can_write:
        raise HttpError(403, "当前账号只读，字头表仅操作员可维护")


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
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能提交刀补")
    try:
        row = accept_submission(
            user=user,
            tool_code=body.tool_code,
            offset_um=body.offset_um,
        )
    except InvalidToolCode as exc:
        # 与页面预拦同口径；直连接口、落库前改写刀号也都在此被退回。
        raise HttpError(400, str(exc))
    return _to_out(row)


@api.get("/prefixes", response=list[PrefixOut], auth=bearer_auth)
def list_prefixes(request: HttpRequest):
    return [
        PrefixOut(
            id=p.id,
            prefix=p.prefix,
            created_by=p.created_by.username if p.created_by_id else None,
            created_at=p.created_at,
        )
        for p in ToolPrefix.objects.select_related("created_by").all()
    ]


@api.post("/prefixes", response=PrefixOut, auth=bearer_auth)
def create_prefix(request: HttpRequest, body: PrefixIn):
    user: User = request.auth
    _require_writer(user)
    try:
        p = add_prefix(user, body.prefix)
    except PrefixAlreadyExists:
        raise HttpError(409, f"字头「{body.prefix.strip()}」已登记")
    except InvalidToolCode as exc:
        raise HttpError(400, str(exc))
    return PrefixOut(
        id=p.id,
        prefix=p.prefix,
        created_by=user.username,
        created_at=p.created_at,
    )


@api.delete("/prefixes/{prefix}", auth=bearer_auth)
def delete_prefix(request: HttpRequest, prefix: str):
    user: User = request.auth
    _require_writer(user)
    try:
        removed = remove_prefix(user, prefix)
    except PrefixMissing:
        raise HttpError(404, f"字头「{prefix}」未登记")
    except InvalidToolCode as exc:
        raise HttpError(400, str(exc))
    return {"deleted": removed}


@api.get("/prefix-changelogs", response=list[PrefixChangeLogOut], auth=bearer_auth)
def list_prefix_changelogs(request: HttpRequest):
    return [
        PrefixChangeLogOut(
            id=log.id,
            prefix=log.prefix,
            action=log.action,
            action_label=log.get_action_display(),
            operator_name=log.operator_name,
            created_at=log.created_at,
        )
        for log in PrefixChangeLog.objects.select_related("operator")[:200]
    ]


@api.get("/rejected-tool-codes", response=list[RejectedOut], auth=bearer_auth)
def list_rejected(request: HttpRequest):
    # 复核员可见退回样例，但无权改动字头（见 _require_writer）。
    return [
        RejectedOut(
            id=r.id,
            tool_code=r.tool_code,
            prefix=r.prefix,
            offset_um=r.offset_um,
            reason=r.reason,
            submitter_name=r.submitter_name,
            created_at=r.created_at,
        )
        for r in RejectedToolCode.objects.all()[:200]
    ]
