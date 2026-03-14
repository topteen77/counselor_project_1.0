"""
Context processors for counselor app (e.g. mobile nav).
Uses session-based auth: request.session.get('id') for CounselorUser.
"""
from .models import CoursePayment


def mobile_nav_context(request):
    """Add nav_is_logged_in and nav_user_has_paid for footer_nav_mobile.html."""
    user_id = getattr(request, 'session', {}).get('id')
    is_logged_in = bool(user_id)
    user_has_paid = False
    if user_id:
        user_has_paid = CoursePayment.objects.filter(user_id=user_id, is_success=True).exists()
    return {
        'nav_is_logged_in': is_logged_in,
        'nav_user_has_paid': user_has_paid,
    }
