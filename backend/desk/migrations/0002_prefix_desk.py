import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("desk", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ToolPrefix",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("prefix", models.CharField(max_length=16, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prefixes_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["prefix"],
            },
        ),
        migrations.CreateModel(
            name="PrefixChangeLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("prefix", models.CharField(db_index=True, max_length=16)),
                (
                    "action",
                    models.CharField(
                        choices=[("add", "新增"), ("remove", "删除")],
                        max_length=8,
                    ),
                ),
                ("operator_name", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "operator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prefix_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="RejectedToolCode",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tool_code", models.CharField(db_index=True, max_length=32)),
                ("prefix", models.CharField(blank=True, db_index=True, default="", max_length=16)),
                ("offset_um", models.IntegerField(blank=True, null=True)),
                ("reason", models.CharField(blank=True, default="", max_length=200)),
                ("submitter_name", models.CharField(blank=True, default="", max_length=150)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="rejected_tool_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddField(
            model_name="offsetsubmission",
            name="prefix",
            field=models.CharField(blank=True, db_index=True, default="", max_length=16),
        ),
    ]
