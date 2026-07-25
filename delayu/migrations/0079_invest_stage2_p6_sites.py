from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0078_invest_stage2_p5_quality"),
    ]

    operations = [
        migrations.AddField(
            model_name="investprojectsite",
            name="booked_until",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Бронь до"),
        ),
        migrations.AddField(
            model_name="investsite",
            name="restriction_zones",
            field=models.JSONField(blank=True, default=list, verbose_name="Ограничительные зоны"),
        ),
    ]
