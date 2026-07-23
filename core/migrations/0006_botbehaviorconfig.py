from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_recommendationdatafile"),
    ]

    operations = [
        migrations.CreateModel(
            name="BotBehaviorConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "instructions",
                    models.TextField(
                        default="Keep guidance practical, supportive, and non-judgmental. Use only the supplied customer profile and recommendation data. Do not provide medical diagnosis or treatment advice."
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_bot_behavior_configs", to="core.user"),
                ),
            ],
        ),
    ]
