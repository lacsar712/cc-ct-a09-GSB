from django.test import TestCase
from ninja.testing import TestClient

from desk.api import api
from desk.auth_utils import create_access_token
from desk.models import (
    OffsetSubmission,
    PrefixChangeLog,
    RejectedToolCode,
    ToolPrefix,
    User,
)
from desk.services import accept_submission, InvalidToolCode, reject_message


class PrefixDeskTests(TestCase):
    def setUp(self):
        self.client = TestClient(api)
        self.machinist = User.objects.create_user(
            username="machinist", password="x", role=User.Role.MACHINIST
        )
        self.auditor = User.objects.create_user(
            username="auditor", password="x", role=User.Role.AUDITOR
        )
        self.mauth = self._auth(self.machinist)
        self.afauth = self._auth(self.auditor)

    def _auth(self, user):
        return {"Authorization": f"Bearer {create_access_token(user)}"}

    def _only_jia(self):
        """登记甲、乙后删掉乙，字头台只留甲。"""
        r1 = self.client.post("/prefixes", json={"prefix": "甲"}, headers=self.mauth)
        self.assertEqual(r1.status_code, 200, r1.content)
        r2 = self.client.post("/prefixes", json={"prefix": "乙"}, headers=self.mauth)
        self.assertEqual(r2.status_code, 200, r2.content)
        rd = self.client.delete("/prefixes/乙", headers=self.mauth)
        self.assertEqual(rd.status_code, 200, rd.content)
        self.assertEqual(
            list(ToolPrefix.objects.values_list("prefix", flat=True)), ["甲"]
        )

    # 只留甲：交甲刀零一应收下，交乙刀零九应退回
    def test_only_jia_accept_jia_reject_yi(self):
        self._only_jia()

        ok = self.client.post(
            "/submissions",
            json={"tool_code": "甲刀零一", "offset_um": 5},
            headers=self.mauth,
        )
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(ok.json()["tool_code"], "甲刀零一")
        self.assertEqual(ok.json()["prefix"], "甲")

        bad = self.client.post(
            "/submissions",
            json={"tool_code": "乙刀零九", "offset_um": 20},
            headers=self.mauth,
        )
        # 直连接口（绕过页面）与页面同口径退回
        self.assertEqual(bad.status_code, 400, bad.content)
        self.assertEqual(
            bad.json()["detail"], reject_message("乙刀零九", "乙")
        )

        # 退回不产生刀补记录，只记退回样例
        self.assertEqual(OffsetSubmission.objects.count(), 1)
        self.assertEqual(OffsetSubmission.objects.get().tool_code, "甲刀零一")
        rej = RejectedToolCode.objects.get()
        self.assertEqual(rej.tool_code, "乙刀零九")
        self.assertEqual(rej.prefix, "乙")

    # 三路径同口径：服务层收口、HTTP 直连、落库前偷改刀号
    def test_three_paths_share_one_rule(self):
        self._only_jia()

        # 路径一：服务层（落库前唯一收口）
        with self.assertRaises(InvalidToolCode) as ctx:
            accept_submission(
                user=self.machinist, tool_code="乙刀零九", offset_um=20
            )
        self.assertEqual(str(ctx.exception), reject_message("乙刀零九", "乙"))

        # 路径二：绕过页面的直连接口
        direct = self.client.post(
            "/submissions",
            json={"tool_code": "乙刀零九", "offset_um": 20},
            headers=self.mauth,
        )
        self.assertEqual(direct.status_code, 400)
        self.assertEqual(direct.json()["detail"], str(ctx.exception))

        # 路径三：落库前若被改写成未登记字头刀号，仍在收口处退回，原样退回不偷改
        tampered = self.client.post(
            "/submissions",
            json={"tool_code": "丙刀七", "offset_um": 1},
            headers=self.mauth,
        )
        self.assertEqual(tampered.status_code, 400)
        self.assertEqual(
            tampered.json()["detail"], reject_message("丙刀七", "丙")
        )
        self.assertFalse(
            OffsetSubmission.objects.filter(tool_code__startswith="甲").exists()
        )
        self.assertEqual(RejectedToolCode.objects.filter(tool_code="丙刀七").count(), 1)

    # 删甲后：再交甲应退回，旧甲刀单刀号原样仍在
    def test_remove_jia_keeps_old_but_rejects_new(self):
        self.client.post("/prefixes", json={"prefix": "甲"}, headers=self.mauth)
        self.client.post(
            "/submissions",
            json={"tool_code": "甲刀零一", "offset_um": 5},
            headers=self.mauth,
        )
        old = OffsetSubmission.objects.get(tool_code="甲刀零一")
        self.assertEqual(old.prefix, "甲")

        rd = self.client.delete("/prefixes/甲", headers=self.mauth)
        self.assertEqual(rd.status_code, 200, rd.content)

        # 旧单刀号不被删字头改写，仍在
        old.refresh_from_db()
        self.assertEqual(old.tool_code, "甲刀零一")
        self.assertEqual(old.prefix, "甲")

        # 再交甲应退回
        again = self.client.post(
            "/submissions",
            json={"tool_code": "甲刀零一", "offset_um": 5},
            headers=self.mauth,
        )
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["detail"], reject_message("甲刀零一", "甲"))
        self.assertEqual(OffsetSubmission.objects.count(), 1)
        self.assertEqual(RejectedToolCode.objects.count(), 1)

    # 字头增删写履历，可做新旧对照
    def test_changelog_records_add_and_remove(self):
        self._only_jia()
        actions = list(
            PrefixChangeLog.objects.filter(prefix="乙")
            .order_by("id")
            .values_list("action", flat=True)
        )
        self.assertEqual(actions, ["add", "remove"])
        for log in PrefixChangeLog.objects.all():
            self.assertEqual(log.operator_name, "machinist")
            self.assertIn(log.get_action_display(), ("新增", "删除"))

    # 复核员：能看字头表、退回样例、履历，但不能改字头
    def test_auditor_read_only(self):
        self._only_jia()
        self.client.post(
            "/submissions",
            json={"tool_code": "乙刀零九", "offset_um": 20},
            headers=self.mauth,
        )

        for path in ("/prefixes", "/prefix-changelogs", "/rejected-tool-codes"):
            r = self.client.get(path, headers=self.afauth)
            self.assertEqual(r.status_code, 200, (path, r.content))

        add = self.client.post(
            "/prefixes", json={"prefix": "丙"}, headers=self.afauth
        )
        self.assertEqual(add.status_code, 403)
        rm = self.client.delete("/prefixes/甲", headers=self.afauth)
        self.assertEqual(rm.status_code, 403)
        sub = self.client.post(
            "/submissions",
            json={"tool_code": "甲刀零一", "offset_um": 1},
            headers=self.afauth,
        )
        self.assertEqual(sub.status_code, 403)
        # 被拒后字头台未变
        self.assertEqual(
            list(ToolPrefix.objects.values_list("prefix", flat=True)), ["甲"]
        )

    def test_duplicate_prefix_conflict(self):
        self.client.post("/prefixes", json={"prefix": "甲"}, headers=self.mauth)
        dup = self.client.post("/prefixes", json={"prefix": "甲"}, headers=self.mauth)
        self.assertEqual(dup.status_code, 409)

    def test_unauthenticated_rejected(self):
        self.assertEqual(self.client.get("/prefixes").status_code, 401)
