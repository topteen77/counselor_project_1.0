
from django.urls import path

from counselor import views 
from counselor.views import *
app_name='counselor'

urlpatterns = [
    path('', login_view, name='login_view'),
    path('login-page/', user_login, name='user_login'),
    path('signup-page/', signup_view, name='signup_view'),
    path('user_signup/', user_signup, name='user_signup'),
    path('user_logout/', user_logout, name='user_logout'),
    path('counsellor-courses/', icef_view, name='icef_view'),
    path('course-overview/<str:course_name>/', course_overview, name='course_overview'),
    # Class-based views
    path('counselor_enrolled_course/', CounselorEnrolledCourseView.as_view(), name='counselor_enrolled_course'),
    path('counselor_enrolled_course/<str:course_name>/', CounselorEnrolledCourseView.as_view(), name='counselor_enrolled_course_param'),
    path('counselor_enrolled_course/<str:course_name>/autocomplete/', quiz_autocomplete, name='quiz_autocomplete'),
    path('counselor_enrolled_course/<str:course_name>/autocomplete-full/', course_autocomplete, name='course_autocomplete'),
    path('fetch_current_part/<str:course_name>/autocomplete/', quiz_autocomplete, name='quiz_autocomplete_activate'),
    path('fetch_current_part/<str:course_name>/<int:current_part_id>/<int:part_or_quiz>/',fetch_current_part, name='fetch_current_part'),
    path('update_part_status/<int:part_id>/',update_part_status,name='update_part_status')
    # path('update_progress/', views.update_progress, name='update_progress'),  # Update progress
    # path('get_progress_and_duration/<str:video_id>/', views.get_progress_and_duration, name='get_progress_and_duration'),  # Get progress

    # path('update_progress/', update_progress, name='update_progress'),  # Update progress
    # path('get_progress_and_duration/<str:video_id>/', get_progress_and_duration, name='get_progress_and_duration'),  # Get progress

    # path("course12/", content_view, name="content_view"),
    # path('my-django-view/', views.my_django_view, name='my_django_view'),
]