from django.db import migrations, models
from delayu.migration_ops import AddFieldIfMissing, AddIndexIfMissing, CreateModelIfMissing


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0078_invest_stage2_p5_quality"),
    ]

    operations = [
        AddFieldIfMissing(
            model_name="investprojectsite",
            name="booked_until",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Бронь до"),
        ),
        AddFieldIfMissing(
            model_name="investsite",
            name="restriction_zones",
            field=models.JSONField(blank=True, default=list, verbose_name="Ограничительные зоны"),
        ),
    ]
