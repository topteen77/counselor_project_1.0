from django.db import migrations


def import_existing_images(apps, schema_editor):
    from counselor.builtin_images import import_builtin_images

    import_builtin_images()


class Migration(migrations.Migration):

    dependencies = [
        ("counselor", "0024_counselorcourse_overview_image"),
    ]

    operations = [
        migrations.RunPython(import_existing_images, migrations.RunPython.noop),
    ]
