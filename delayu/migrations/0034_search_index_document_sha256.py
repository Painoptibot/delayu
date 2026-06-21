from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0033_userprofile_totp_secret"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentfile",
            name="content_sha256",
            field=models.CharField(blank=True, db_index=True, max_length=64, verbose_name="SHA-256"),
        ),
        migrations.CreateModel(
            name="SearchIndexEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(db_index=True, max_length=32)),
                ("object_id", models.PositiveIntegerField()),
                ("title", models.CharField(max_length=500)),
                ("body", models.TextField(blank=True)),
                ("content_hash", models.CharField(blank=True, max_length=64)),
                ("indexed_at", models.DateTimeField(auto_now=True)),
                (
                    "subsystem",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="search_index",
                        to="delayu.subsystem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Поисковый индекс",
                "verbose_name_plural": "Поисковый индекс",
                "ordering": ["-indexed_at"],
                "unique_together": {("subsystem", "kind", "object_id")},
            },
        ),
    ]
