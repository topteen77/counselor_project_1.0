
from django.urls import path

from counselor import views 
from counselor.views import *
# Import new production-ready views
from counselor.views_v2 import (
    CounselorEnrolledCourseViewV2,
    FetchCurrentPartViewV2,
    update_part_status as update_part_status_v2
)
app_name='counselor'

urlpatterns = [
    path('', icef_view, name='landing'),  # Course list with prices as landing page
    path('login/', login_view, name='login_view'),
    path('login-page/', user_login, name='user_login'),
    path('signup-page/', signup_view, name='signup_view'),
    path('user_signup/', user_signup, name='user_signup'),
    path('forgot-password/', forgot_password_view, name='forgot_password'),
    path('reset-password/', reset_password_view, name='reset_password'),
    path('user_logout/', user_logout, name='user_logout'),
    path('counsellor-courses/', icef_view, name='icef_view'),
    path('course-overview/<str:course_name>/', course_overview, name='course_overview'),
    # Payment
    path('course/<str:course_name>/payment/', course_payment_view, name='course_payment'),
    path('course/<str:course_name>/create-order/', create_course_order, name='create_course_order'),
    path('update_counselor_course_payment/', update_counselor_course_payment, name='update_counselor_course_payment'),
    path('course_payment_success/<path:enc_id>/', course_payment_success_view, name='course_payment_success'),
    path('course_payment_fail/<path:enc_id>/', course_payment_fail_view, name='course_payment_fail'),
    path('receipt/<int:payment_id>/download/', receipt_download_view, name='receipt_download'),
    # Production-ready class-based views
    path('counselor_enrolled_course/', CounselorEnrolledCourseViewV2.as_view(), name='counselor_enrolled_course'),
    path('counselor_enrolled_course/<str:course_name>/', CounselorEnrolledCourseViewV2.as_view(), name='counselor_enrolled_course_param'),
    path('counselor_enrolled_course/<str:course_name>/trial-expired-back/', trial_expired_back, name='trial_expired_back'),
    path('counselor_enrolled_course/<str:course_name>/autocomplete/', quiz_autocomplete, name='quiz_autocomplete'),
    path('counselor_enrolled_course/<str:course_name>/autocomplete-full/', course_autocomplete, name='course_autocomplete'),
    path('fetch_current_part/<str:course_name>/autocomplete/', quiz_autocomplete, name='quiz_autocomplete_activate'),
    path('fetch_current_part/<str:course_name>/<int:current_part_id>/<int:part_or_quiz>/', FetchCurrentPartViewV2.as_view(), name='fetch_current_part'),
    path('update_part_status/<int:part_id>/', update_part_status_v2, name='update_part_status')
    # path('update_progress/', views.update_progress, name='update_progress'),  # Update progress
    # path('get_progress_and_duration/<str:video_id>/', views.get_progress_and_duration, name='get_progress_and_duration'),  # Get progress

    # path('update_progress/', update_progress, name='update_progress'),  # Update progress
    # path('get_progress_and_duration/<str:video_id>/', get_progress_and_duration, name='get_progress_and_duration'),  # Get progress

    # path("course12/", content_view, name="content_view"),
    # path('my-django-view/', views.my_django_view, name='my_django_view'),
]