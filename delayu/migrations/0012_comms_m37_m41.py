# M37–M41 communications

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0011_bpm_m33_m36"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="comment",
            name="parent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="replies",
                to="delayu.comment",
            ),
        ),
        migrations.CreateModel(
            name="MessengerChannel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("channel_type", models.CharField(choices=[("telegram", "Telegram"), ("max", "MAX"), ("other", "Другое")], max_length=16)),
                ("webhook_url", models.CharField(blank=True, max_length=500)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messenger_channels", to="delayu.subsystem")),
            ],
            options={"verbose_name": "Канал мессенджера", "unique_together": {("subsystem", "code")}},
        ),
        migrations.CreateModel(
            name="VideoMeeting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("meeting_url", models.URLField(blank=True, max_length=500)),
                ("scheduled_at", models.DateTimeField()),
                ("protocol_notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="meetings", to="delayu.casefile")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="meetings_created", to=settings.AUTH_USER_MODEL)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="video_meetings", to="delayu.subsystem")),
            ],
            options={"verbose_name": "Видеосовещание", "ordering": ["-scheduled_at"]},
        ),
        migrations.CreateModel(
            name="Mention",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("excerpt", models.CharField(blank=True, max_length=200)),
                ("link_path", models.CharField(blank=True, max_length=500)),
                ("is_read", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mentions_sent", to=settings.AUTH_USER_MODEL)),
                ("chat_message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mentions", to="delayu.chatmessage")),
                ("comment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="mentions", to="delayu.comment")),
                ("mentioned_user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mentions_received", to=settings.AUTH_USER_MODEL)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="mentions", to="delayu.subsystem")),
            ],
            options={"verbose_name": "Упоминание", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ObjectSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_type", models.CharField(choices=[("case", "Дело"), ("document", "Документ")], max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("case", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to="delayu.casefile")),
                ("document", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to="delayu.documentfile")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="delayu.subsystem")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="object_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "Подписка на объект"},
        ),
    ]
