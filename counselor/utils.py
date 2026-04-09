"""Shared helpers for counselor app."""
from .models import SiteLabel


def completed_course_step_count(course_with_related_data, introduction_id, user_progress, found):
    """
    One step per non-introduction part. Counts complete when:
    - Part has quiz(es): user has a quiz result for that part (found[part_id] is true).
    - Part has no quiz: part is marked complete in CourseContentProgress (user_progress).
    """
    if not course_with_related_data:
        return 0
    intro = set(introduction_id)
    done = set(user_progress)
    n = 0
    for chapter in course_with_related_data.chapters.all():
        for part in chapter.parts.all():
            if part.id in intro:
                continue
            if part.quizzes.exists():
                if found.get(part.id):
                    n += 1
            elif part.id in done:
                n += 1
    return n


def completed_course_step_count_from_progress(progress_data):
    """
    Same completion rules as completed_course_step_count, using the dict from
    UserProgressService (includes parts_with_quizzes).
    """
    if not progress_data:
        return 0
    part_ids = progress_data.get('part_ids') or []
    intro = set(progress_data.get('introduction_id') or [])
    done = set(progress_data.get('user_progress') or [])
    found = progress_data.get('found') or {}
    quiz_parts = progress_data.get('parts_with_quizzes') or set()
    n = 0
    for part_id in part_ids:
        if part_id in intro:
            continue
        if part_id in quiz_parts:
            if found.get(part_id):
                n += 1
        elif part_id in done:
            n += 1
    return n

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
