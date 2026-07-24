from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_botbehaviorconfig"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerBotBehaviorOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("instructions", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_customer_bot_behavior_overrides", to="core.user"),
                ),
                (
                    "user",
                    models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="bot_behavior_override", to="core.user"),
                ),
            ],
            options={
                "ordering": ["user_id"],
            },
        ),
        migrations.CreateModel(
            name="BotBehaviorRevision",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(choices=[("global", "Global"), ("customer", "Customer")], max_length=20)),
                ("instructions", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "customer",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="bot_behavior_revisions", to="core.user"),
                ),
                (
                    "updated_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_bot_behavior_revisions", to="core.user"),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
