from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("counselor", "0023_counselorcourse_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="counselorcourse",
            name="overview_image",
            field=models.FileField(
                blank=True,
                help_text="Photo shown on the course overview page. Leave empty to use the existing image for this country, if one exists.",
                null=True,
                upload_to="course_overview_images/",
            ),
        ),
    ]
