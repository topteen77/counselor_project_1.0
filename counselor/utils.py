"""Shared helpers for counselor app."""
from .models import SiteLabel

DEFAULT_SITE_LABELS = {
    'start_course': 'Start course',
    'start_trial': 'Start Trial',
    'start_trial_login_required': 'Start Trial (%s min) — Login required',
    'view_detail': 'View detail',
    'pay_now': 'Pay now',
    'trial_ended_ribbon': 'Trial ended',
    'book_course': 'Book course',
    'download_invoice': 'Download Invoice',
    'resume_course': 'Resume Course',
    'resume': 'Resume',
    'buy_now': 'Buy now',
    'back_to_course_list': 'Back to course list',
    'trial_expired_title': 'Trial expired',
    'trial_expired_message': 'Your trial has ended. Pay for the course to unlock all content and continue learning.',
    'trial_expired_instruction': 'Click Buy now to complete payment and get full access.',
    'view_certificate': 'View Certificate',
}


def get_site_labels():
    """Return dict of label key -> value. DB values override defaults."""
    out = dict(DEFAULT_SITE_LABELS)
    try:
        for row in SiteLabel.objects.all().values_list('key', 'value'):
            out[row[0]] = row[1]
    except Exception:
        pass
    return out
