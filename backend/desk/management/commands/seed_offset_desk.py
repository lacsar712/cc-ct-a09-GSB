from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from desk.auth_utils import hash_password
from desk.models import (
    OffsetSubmission,
    PrefixChangeLog,
    ToolPrefix,
    User,
)

INITIAL_PREFIXES = ["甲", "乙"]


class Command(BaseCommand):
    help = "创建默认账号、初始字头与种子刀补记录"

    @transaction.atomic
    def handle(self, *args, **options):
        machinist, _ = User.objects.update_or_create(
            username="machinist",
            defaults={
                "role": User.Role.MACHINIST,
                "password": hash_password("machine123456"),
                "is_active": True,
            },
        )
        User.objects.update_or_create(
            username="auditor",
            defaults={
                "role": User.Role.AUDITOR,
                "password": hash_password("audit123456"),
                "is_active": True,
            },
        )

        for prefix in INITIAL_PREFIXES:
            obj, created = ToolPrefix.objects.get_or_create(
                prefix=prefix,
                defaults={"created_by": machinist},
            )
            if created or not PrefixChangeLog.objects.filter(
                prefix=prefix, action=PrefixChangeLog.Action.ADD
            ).exists():
                PrefixChangeLog.objects.create(
                    prefix=prefix,
                    action=PrefixChangeLog.Action.ADD,
                    operator=machinist,
                    operator_name=machinist.username,
                )

        now = timezone.now()
        seeds = [
            ("T01", 5, OffsetSubmission.Verdict.PASS),
            ("T09", 20, OffsetSubmission.Verdict.FAIL),
        ]
        for tool_code, offset_um, verdict in seeds:
            OffsetSubmission.objects.update_or_create(
                tool_code=tool_code,
                offset_um=offset_um,
                defaults={
                    "status": OffsetSubmission.Status.DONE,
                    "verdict": verdict,
                    "submitted_by": machinist,
                    "reviewed_at": now,
                },
            )

        self.stdout.write(self.style.SUCCESS("seed_offset_desk 完成"))
