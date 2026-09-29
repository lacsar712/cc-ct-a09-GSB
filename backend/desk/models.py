from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MACHINIST = "machinist", "操作员"
        AUDITOR = "auditor", "复核员"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MACHINIST,
    )

    @property
    def can_write(self) -> bool:
        return self.role == self.Role.MACHINIST


class ToolPrefix(models.Model):
    """字头台登记的字头。刀号必须以登记过的字头起笔，否则退回。"""

    prefix = models.CharField(max_length=16, unique=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prefixes_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["prefix"]

    def __str__(self) -> str:
        return self.prefix


class PrefixChangeLog(models.Model):
    """字头增删改动履历。已收下的旧刀号不因删字头被改写，履历可做新旧对照。"""

    class Action(models.TextChoices):
        ADD = "add", "新增"
        REMOVE = "remove", "删除"

    prefix = models.CharField(max_length=16, db_index=True)
    action = models.CharField(max_length=8, choices=Action.choices)
    operator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prefix_changes",
    )
    operator_name = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.get_action_display()}字头 {self.prefix}"


class RejectedToolCode(models.Model):
    """不合字头被退回的刀号样例，供字头台展示，复核员可见不可改。"""

    tool_code = models.CharField(max_length=32, db_index=True)
    prefix = models.CharField(max_length=16, blank=True, default="", db_index=True)
    offset_um = models.IntegerField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True, default="")
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rejected_tool_codes",
    )
    submitter_name = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"退回 {self.tool_code}"


class OffsetSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待复核"
        PROCESSING = "processing", "复核中"
        DONE = "done", "已完成"

    class Verdict(models.TextChoices):
        PASS = "合格", "合格"
        FAIL = "超差", "超差"

    tool_code = models.CharField(max_length=32, db_index=True)
    prefix = models.CharField(max_length=16, blank=True, default="", db_index=True)
    offset_um = models.IntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    verdict = models.CharField(
        max_length=8,
        choices=Verdict.choices,
        blank=True,
        default="",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.tool_code} {self.offset_um}µm"
