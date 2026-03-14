# Generated migration for trial-expired acknowledgement

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('counselor', '0021_discountcoupon_courses_m2m'),
    ]

    operations = [
        migrations.AddField(
            model_name='coursetrialstart',
            name='expired_acknowledged_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
