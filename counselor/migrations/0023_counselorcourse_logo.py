from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("counselor", "0022_coursetrialstart_expired_acknowledged_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="counselorcourse",
            name="logo",
            field=models.FileField(
                blank=True,
                help_text="Country flag shown on the course card. SVG, PNG, or JPG. Leave empty to use the built-in flag for this country, if one exists.",
                null=True,
                upload_to="course_logos/",
            ),
        ),
    ]
