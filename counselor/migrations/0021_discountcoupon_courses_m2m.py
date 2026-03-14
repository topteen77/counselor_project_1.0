# Generated migration: same coupon can apply to multiple courses

from django.db import migrations, models


def copy_course_to_courses(apps, schema_editor):
    """Copy old course FK into the new courses M2M for existing coupons."""
    DiscountCoupon = apps.get_model('counselor', 'DiscountCoupon')
    for coupon in DiscountCoupon.objects.all():
        if coupon.course_id:
            coupon.courses.add(coupon.course_id)


def reverse_course_from_courses(apps, schema_editor):
    """Reverse: set course to first course in M2M if any (best-effort)."""
    DiscountCoupon = apps.get_model('counselor', 'DiscountCoupon')
    for coupon in DiscountCoupon.objects.all():
        first = coupon.courses.first()
        coupon.course_id = first.id if first else None
        coupon.save(update_fields=['course_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('counselor', '0020_site_label'),
    ]

    operations = [
        migrations.AddField(
            model_name='discountcoupon',
            name='courses',
            field=models.ManyToManyField(
                blank=True,
                help_text='Leave empty for all courses; otherwise this coupon applies only to selected courses.',
                related_name='coupons',
                to='counselor.counselorcourse',
            ),
        ),
        migrations.RunPython(copy_course_to_courses, reverse_course_from_courses),
        migrations.RemoveField(
            model_name='discountcoupon',
            name='course',
        ),
    ]
