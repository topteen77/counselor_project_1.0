import ast
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render
from datetime import datetime, date, timedelta
import json
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from .models import CounselorCertification, CounselorUser, CourseOverviewSummary, Question, Quiz, Chapter, Part, QuizAnswers, QuizResults ,CourseContentProgress, CounselorCourse, UserProgressTrack, UserQuizAttemptTrack
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Count
from django.utils import timezone
from django.views import View
from django.contrib.auth import get_user_model
from django.views.decorators.csrf import csrf_exempt
from counselor.templatetags.custom_filters import get
import logging
logger = logging.getLogger(__name__)
from django.shortcuts import HttpResponse,HttpResponseRedirect
from django.db.models import Prefetch
User = get_user_model()

def login_view(request):
    return render(request, 'login.html')

def signup_view(request):
    return render(request,'register.html')

def user_logout(request):
    if request.session.get('id'):
        del request.session['id']
    return redirect('counselor:login_view')

def icef_view(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    
    # Get user
    user_id = request.session.get('id')
    user = CounselorUser.objects.only('id').get(id=user_id)
    
    # List of all courses
    course_list = ['Germany', 'UK', 'USA', 'Singapore', 'Newzealand', 'Ireland', 'France', 'Dubai', 'Canada', 'Australia']
    
    # Calculate course status for each course
    course_statuses = {}
    for course_name in course_list:
        try:
            course = CounselorCourse.objects.only('id', 'title').get(title=course_name)
            
            # Check if certificate exists (course is complete)
            try:
                certificate = CounselorCertification.objects.only('id', 'grade', 'certificate_code', 'created_at').get(
                    user=user, course=course
                )
                # Only mark as complete if certificate actually exists
                course_statuses[course_name] = {
                    'status': 'complete',
                    'has_certificate': True,
                    'certificate_code': certificate.certificate_code,
                    'grade': certificate.grade,
                    'issued_date': certificate.created_at.strftime('%d-%m-%Y')
                }
            except CounselorCertification.DoesNotExist:
                # No certificate - check if course is in progress (has some progress)
                course_with_related_data = get_course_with_related_data(course_name)
                if course_with_related_data:
                    total_parts, part_ids, user_progress, scores, found, answers_data, part_scores, correct_answers, incorrect_answers, complete_status, introduction_id, user_progress_quiz = getUserProgress(user, course_with_related_data, course_name)
                    
                    # Filter user_progress to only include parts from THIS course
                    course_part_ids = set(part_ids)
                    course_user_progress = [pid for pid in user_progress if pid in course_part_ids]
                    
                    # Filter scores to only include scores from THIS course
                    # Scores are from QuizResults which is already filtered by course in getUserProgress
                    course_scores = [s for s in scores if s.get('part_id') in course_part_ids] if scores else []
                    
                    # Check if user has any progress in THIS specific course
                    has_progress = len(course_user_progress) > 0 or len(course_scores) > 0
                    
                    if has_progress:
                        course_statuses[course_name] = {
                            'status': 'inprocess',
                            'has_certificate': False
                        }
                    else:
                        course_statuses[course_name] = {
                            'status': 'not_started',
                            'has_certificate': False
                        }
                else:
                    course_statuses[course_name] = {
                        'status': 'not_started',
                        'has_certificate': False
                    }
        except CounselorCourse.DoesNotExist:
            course_statuses[course_name] = {
                'status': 'not_started',
                'has_certificate': False
            }
        except Exception as e:
            # Log error and default to not_started
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error calculating status for course {course_name}: {str(e)}")
            course_statuses[course_name] = {
                'status': 'not_started',
                'has_certificate': False
            }
    
    context = {
        'course_statuses': course_statuses
    }
    
    return render(request, 'icef-course.html', context)

@csrf_exempt
def update_part_status(request, part_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    if not request.session.get('id'):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)
    
    try:
        user_id = request.session.get('id')
        Counselor_user = CounselorUser.objects.get(id=user_id)
        part = Part.objects.get(id=part_id)
        CourseContentProgress.objects.update_or_create(user=Counselor_user, part_id=part, defaults={'completed': True})
        return JsonResponse({'success': True, 'message': 'Part marked as complete'})
    except CounselorUser.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)
    except Part.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Part not found'}, status=404)
    except Exception as e:
        logger.error(f"Error updating part status: {str(e)}")
        return JsonResponse({'success': False, 'message': 'Internal server error'}, status=500)

def user_login(request):
    if request.method == "POST":
        username = request.POST.get('Username')
        password = request.POST.get('password')
        try:
            user = CounselorUser.objects.get(email=username)
            if user.password == password:  # Use Django's password hashing in production
                # print(user.id)    
                request.session['id'] = user.id
                # messages.success(request, "Login successful!")
                return redirect('counselor:icef_view')  # Replace 'home' with the desired URL name
            else:
                messages.error(request, "Incorrect password!")
        except CounselorUser.DoesNotExist:
            messages.error(request, "Username not found.")
    list(messages.get_messages(request))
    return render(request, 'login.html')

def user_signup(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        # Check if passwords match
        if password != confirm_password:
            messages.error(request, "Passwords do not match!")
            return redirect('counselor:user_signup')
        # Save user details
        try:
            user = CounselorUser(username=username, email=email, password=password)
            user.save()
            messages.success(request, "Registration successful! Please log in.")
            return redirect('counselor:login_view')  # Redirect to login page after successful signup
        except IntegrityError:
            messages.error(request, "The email or username is already in use. Please try another.")
            return redirect('counselor:user_signup')
    return render(request, 'register.html')

def get_course_with_related_data(course_name):
    course_with_related_data = []
    try:
        # Prefetch parts, their quizzes, questions, and answers
    #     course_with_related_data = CounselorCourse.objects.prefetch_related(
    #     'chapters__parts__quizzes__questions__answers'
    # ).filter(
    #     title=course_name
    # ).first()

        course_with_related_data = CounselorCourse.objects.prefetch_related(
            Prefetch(
                'chapters',
                queryset=Chapter.objects.order_by('index')  # full data (or required fields) for chapters
            ),
            Prefetch(
                'chapters__parts',
                queryset=Part.objects.only('id','title','index','chapter_id')
            ),
            Prefetch(
                'chapters__parts__quizzes',
                queryset=Quiz.objects.all()
            ),
            Prefetch(
                'chapters__parts__quizzes__questions',
                queryset=Question.objects.all()
            ),
            Prefetch(
                'chapters__parts__quizzes__questions__answers',
                queryset=QuizAnswers.objects.all()
            )
        ).only('id', 'title').filter(
            title=course_name
        ).first()

        # course_with_related_data = CounselorCourse.objects.prefetch_related(
        #     Prefetch(
        #         'chapters',
        #         queryset=Chapter.objects.order_by('index')  # <-- order chapters by index
        #     ),
        #     'chapters__parts__quizzes__questions__answers'
        # ).filter(
        #     title=course_name
        # ).first()
        
    except Chapter.DoesNotExist:
        course_with_related_data = []
    return course_with_related_data

def getUserProgress(user,course_with_related_data,course_name):
    total_parts=0
    part_ids=[]
    introduction_id=[]
    resume_chapter_id=None
    scores = []
    found = {}
    answers_data = {}  # To store correct and incorrect counts for each part
    part_scores = []
    correct_answers = []
    incorrect_answers = []
    complete_status=[]
    correct_selected = {}
    scores=[]
    user_progress_quiz ={}

    try:
        # OPTIMIZATION: Use already prefetched data instead of count() queries
        # Data is already in memory from prefetch_related
        part_ids = [part.id for chapter in course_with_related_data.chapters.all() for part in chapter.parts.all()]
        total_parts = len(part_ids)
        # OPTIMIZATION: Single query with values_list instead of multiple queries
        user_progress = list(CourseContentProgress.objects.filter(user=user).values_list('part_id', flat=True))
        user_progress_quiz = {}
        
    except Exception as e:
        total_parts = 0
        part_ids = []
        user_progress = []

    # OPTIMIZATION: Use only() to reduce data fetched (don't need related objects)
    try:
        course = get_object_or_404(CounselorCourse, title=course_name)
        quiz_result = QuizResults.objects.only('scores', 'user_id', 'course_id').get(user_id=user, course=course)
    except QuizResults.DoesNotExist:
        quiz_result = None

    try:
        if quiz_result is not None:
            scores = quiz_result.scores if isinstance(quiz_result.scores, list) else []
        for chapter in course_with_related_data.chapters.all():
            for part in chapter.parts.all():
                if part.title == 'Introduction':
                    introduction_id.append(part.id)
                part_scores = []
                # part_scores_ids=[]
                for score in scores:
                    if score.get('part_id') == part.id:
                        part_scores.append(score)
                        user_progress_quiz[part.id]=score.get('quiz_id')
                # print("part Scores: ",part_scores_ids)
                # Extract correct and incorrect counts from the scores
                # Handle both autocomplete format and regular quiz submission format
                correct_count = 0
                incorrect_count = 0
                for score in part_scores:
                    if 'quiz_result' in score and isinstance(score['quiz_result'], dict):
                        # Regular quiz submission format
                        correct_count += score['quiz_result'].get('correct_answers', 0)
                        incorrect_count += score['quiz_result'].get('incorrect_answers', 0)
                    elif 'correct_answers' in score:
                        # Autocomplete format (simpler structure)
                        correct_count += score.get('correct_answers', 0)
                        # For autocomplete, incorrect is 0 (all correct)
                        incorrect_count += score.get('incorrect_answers', 0)
                found[part.id] = bool(part_scores)  # Mark as found if there are scores for this part
                if resume_chapter_id is None and not(bool(part_scores)) and not(part.id in introduction_id):
                    resume_chapter_id=chapter.id
                answers_data[part.id] = {
                    'correct': correct_count,
                    'incorrect': incorrect_count
                }
                # Lists to hold correct and incorrect answers
                correct_answers = []
                incorrect_answers = []
                # Loop through the part_scores (already filtered for this part)
                for quiz in part_scores:
                    part_id = quiz.get('part_id')
                    # Check if 'correct_option' exists in the quiz dictionary
                    if 'correct_option' in quiz and isinstance(quiz['correct_option'], dict):
                        for question_key, question_data in quiz['correct_option'].items():
                            if isinstance(question_data, dict):
                                correct_answer = question_data.get('correct_ans')
                                selected_answer = question_data.get('selected_ans')
                                correct_selected[part.id] = {
                                    'correct_answer': correct_answer,
                                    'selected_answer': selected_answer
                                }
                                # Append to the correct or incorrect list
                                if selected_answer == correct_answer:
                                    correct_answers.append((part_id, question_key, correct_answer, selected_answer))
                                else:
                                    incorrect_answers.append((part_id, question_key, correct_answer, selected_answer))
    except QuizResults.DoesNotExist:
        print("QuizResults object does not exist for the current user.")
        scores = []
        found = {}
        answers_data = {}
        part_scores = []
        correct_answers = []
        incorrect_answers = []
        complete_status=[]
        correct_selected = {}
            

    return total_parts,part_ids,user_progress,scores,found,answers_data,part_scores,correct_answers,incorrect_answers,complete_status,introduction_id,user_progress_quiz

def course_overview(request,course_name):
    course_overview_with_related_data=[]
    intro=''
    conclusion=''
    resume=0
    try:
        # Prefetch parts, their quizzes, questions, and answers
        course_overview_with_related_data = CounselorCourse.objects.prefetch_related(
        'chapters__parts'
    ).filter(
        title=course_name
    ).first()
        summaries = CourseOverviewSummary.objects.filter(course__title=course_name).values('title1', 'title2')
        intro=summaries[0]['title1']
        conclusion=summaries[0]['title2']
    except Chapter.DoesNotExist:
        course_overview_with_related_data = []

    user = CounselorUser.objects.get(id=request.session.get('id'))
    course = CounselorCourse.objects.get(title=course_name)
    exists = UserProgressTrack.objects.filter(user=user, course=course).first()
    # print("Exists: ",exists.resume_part.id)

    if exists:
        resume=1

    course_with_related_data = get_course_with_related_data(course_name)
    total_parts, part_ids, user_progress, scores, found, answers_data, part_scores, correct_answers, incorrect_answers, complete_status, introduction_id,user_progress_quiz = getUserProgress(user,course_with_related_data,course_name)

    total_parts=total_parts-len(introduction_id)
    completed_parts=list(set(part_ids) & set(user_progress))
    number_of_completed_parts= len(list(set(completed_parts) - set(introduction_id)))
    completed_percent_value = int((number_of_completed_parts/total_parts)*100)
    context={
        'course': course_overview_with_related_data,
        'image_name': 'ukcourse',
        'intro': intro,
        'conclusion': conclusion,
        'resume': resume,
        'total_parts':total_parts,
        'number_of_completed_parts':number_of_completed_parts,
        'completed_percent_value':completed_percent_value,
    }
    return render(request, 'course-overview.html', context)
    
def fetch_current_part(request,course_name,current_part_id,part_or_quiz):
    template_name = 'counselor-enrolled-course.html'
    course_with_related_data=''
    course_title=''
    certificate_grant=''
    user_name=''
    grade=''
    scores = []
    found = {}
    answers_data = {} 
    part_scores = []
    correct_answers = []
    incorrect_answers = []
    user_progress=[]
    introduction_id=[]
    resume_chapter_id=None
    total_parts=0

    if not request.session.get('id'):
        return redirect('counselor:login_view')
    
    user_id = request.session.get('id')
    # OPTIMIZATION: Use get() with only() instead of filter().first()
    counselor_user = CounselorUser.objects.only('id', 'username').get(id=user_id)
    user_name = counselor_user.username
    # OPTIMIZATION: Use only() to reduce data fetched
    course = CounselorCourse.objects.only('id', 'title').get(title=course_name)
    # Prefetch parts, their quizzes, questions, and answers
    course_with_related_data = get_course_with_related_data(course_name)
    total_parts, part_ids, user_progress, scores, found, answers_data, part_scores, correct_answers, incorrect_answers, complete_status, introduction_id,user_progress_quiz = getUserProgress(user_id,course_with_related_data,course_name)

    course_title=''
    if course_name=='UK':
        course_title='UK Agent and Counsellor Training Course'
    elif course_name=='Germany':
        course_title='Germany Agent and Counsellor Training Course'

    ####################User progress Status########################
    print("User Progress Quiz: ", user_progress_quiz)
    total_parts=total_parts-len(introduction_id)
    completed_parts=list(set(part_ids) & set(user_progress))
    number_of_completed_parts= len(list(set(completed_parts) - set(introduction_id)))
    completed_percent_value = int((number_of_completed_parts/total_parts)*100)
    #################### To grant certificate #################### 
    certificate_grant=True

    ############### To Resume test #######################
    show_part_id=current_part_id
    show_quiz_id=-1
    
    # NEW: Check if quiz is completed (has results saved) - check early
    quiz_completed = False
    if current_part_id in found and found[current_part_id]:
        # Quiz has results, so it's completed
        quiz_completed = True
    
    if part_or_quiz == 0:
        # User clicked quiz button - check if quiz is unlocked (part must be completed)
        if current_part_id in complete_status:
            # Part is completed, quiz is accessible
            # If quiz is already completed, show results; otherwise show quiz form
            if quiz_completed:
                # Quiz is completed - show results screen
                show_quiz_id = current_part_id
            else:
                # Part completed but quiz not taken - show quiz form
                show_quiz_id = current_part_id
        else:
            # Quiz is locked, show part content instead
            show_quiz_id = -1
            show_part_id = current_part_id
    
    # OPTIMIZATION: Reuse counselor_user instead of querying again
    user = counselor_user
    
    # OPTIMIZATION: Use select_related to avoid extra query for chapter
    # Note: Don't use .only() when we need to access chapter relationship
    part = Part.objects.select_related('chapter').get(id=show_part_id)
    resume_chapter_id = part.chapter.id

    # OPTIMIZATION: Reuse part object instead of querying again
    part_content_testing = part
    # OPTIMIZATION: Single query with prefetch_related
    quiz_content_testing = Part.objects.prefetch_related(
        'quizzes__questions__answers'
    ).only('id').filter(
        id=show_part_id
    ).first()
    
    # Fix: Handle case where part_or_quiz=1 but user is trying to access a quiz
    # Check if part has quizzes and part is completed (quiz should be unlocked)
    if part_or_quiz == 1 and quiz_content_testing and quiz_content_testing.quizzes.exists():
        if show_part_id in complete_status:
            # Part is completed, so quiz should be accessible
            # If quiz is already completed, show results instead of quiz form
            if quiz_completed:
                # Quiz is completed - show results screen
                show_quiz_id = current_part_id
            else:
                # Part is completed but quiz not taken yet - show quiz form
                show_quiz_id = current_part_id
        else:
            # Quiz is locked (part not completed), redirect to the part content instead
            show_quiz_id = -1
            show_part_id = current_part_id

    resume_id, time_difference , no_of_attempt, window_closed_time=show_reattempt_or_not(user,course,current_part_id,found,introduction_id)
    print("Show part id: ",show_part_id)
    print("Show quiz id: ",show_quiz_id)
    
    # Ensure quiz_content_testing is set correctly when showing a quiz
    if show_quiz_id != -1 and show_quiz_id is not None:
        # If we're showing a quiz, make sure quiz_content_testing is set to that part
        if not quiz_content_testing or quiz_content_testing.id != show_quiz_id:
            quiz_content_testing = Part.objects.prefetch_related(
                'quizzes__questions__answers'
            ).only('id').filter(
                id=show_quiz_id
            ).first()

    # Check if autocomplete is enabled for this course
    autocomplete_enabled = request.session.get(f'autocomplete_{course_name}', False)

    # Get next part after current part
    next_part = None
    # Build list with chapter index for sorting
    all_parts_ordered = []
    for chapter in course_with_related_data.chapters.all():
        chapter_index = chapter.index  # Get index from prefetched chapter
        for part in chapter.parts.all():
            # Store tuple with (chapter_index, part_index, part) for sorting
            all_parts_ordered.append((chapter_index, part.index, part))
    # Sort by chapter index, then part index
    all_parts_ordered.sort(key=lambda x: (x[0], x[1]))
    # Extract just the parts after sorting
    all_parts_ordered = [part for _, _, part in all_parts_ordered]
    
    current_part_index = None
    for idx, part in enumerate(all_parts_ordered):
        if part.id == show_part_id:
            current_part_index = idx
            break
    
    if current_part_index is not None and current_part_index < len(all_parts_ordered) - 1:
        next_part = all_parts_ordered[current_part_index + 1]
    
    # Get next part for completed quiz "Next" button
    next_part_for_quiz = None
    if quiz_completed and show_quiz_id == current_part_id:
        # If quiz is completed, use the same next_part
        next_part_for_quiz = next_part

    if resume_chapter_id is None:
        resume_chapter_id=course_with_related_data.chapters.all()[0].id
    
    context = {
        'course': course_with_related_data,
        'scores':scores,
        'found' : found,
        'answers_data': answers_data,
        'part_scores': part_scores,
        'correct_answers':correct_answers,
        'incorrect_answers':incorrect_answers,
        'complete_status':user_progress,
        'course_title':course_title,
        'certificate_grant':certificate_grant,
        'user_name':user_name,
        'show_part_id':show_part_id,
        'show_quiz_id':show_quiz_id,
        'resume_chapter_id':resume_chapter_id,
        'total_parts':total_parts,
        'number_of_completed_parts':number_of_completed_parts,
        'completed_percent_value':completed_percent_value,
        'part_content_testing':part_content_testing,
        'quiz_content_testing':quiz_content_testing,
        'no_of_attempt':no_of_attempt,
        'autocomplete_enabled': autocomplete_enabled,
        'course_name': course_name,
        'next_part': next_part,
        'quiz_completed': quiz_completed,  # NEW: Add quiz completion status
        'next_part_for_quiz': next_part_for_quiz,  # NEW: Next part when viewing completed quiz
        # NEW: Calculate quiz pass/fail status for current quiz
        'quiz_passed': False,  # Will be calculated if needed
        'quiz_pass_status': {},  # Dictionary to store pass status for each part
        'has_passed_quiz': False,  # Whether user has passed (attempt track deleted)
        'show_next_button': False,  # Whether to show Next button
        'show_reattempt_button': False,  # Whether to show Re-attempt button
    }

    return render(request,template_name, context)

def show_reattempt_or_not(user, course, part_id, found, introduction_id):
    """
    OPTIMIZED: Prefetches all UserQuizAttemptTrack records in single query
    instead of multiple queries per part. Reduces N+1 query problem.
    """
    resume_id = -1
    window_closed_time = None
    current_time = None
    time_difference = None
    give_reattempt = 0
    
    logger.debug("Reattempt or not")
    
    if len(found) == 0:
        resume_id = part_id
    else:
        # OPTIMIZATION: Prefetch all attempt tracks for user and course in single query
        part_ids = list(found.keys())
        attempt_tracks = {
            track.part_id: track 
            for track in UserQuizAttemptTrack.objects.filter(
                user=user, 
                course=course,
                part_id__in=part_ids
            ).only('part_id', 'no_of_attempt', 'window_closed_time')
        }
        
        for key, value in found.items():
            attempt_track = attempt_tracks.get(key)
            
            if attempt_track:
                logger.debug("Found attempt track")
                resume_id = attempt_track.part_id
                
                if attempt_track.no_of_attempt == 3:
                    give_reattempt = 3
                    logger.debug("H1")
                    continue
                elif attempt_track.no_of_attempt == 2:
                    window_closed_time = attempt_track.window_closed_time
                    give_reattempt = 2
                    logger.debug("H2")
                    break
                else:
                    give_reattempt = 1
                    break
            elif value == False and not (key in introduction_id):
                resume_id = key
                logger.debug("H3")
                break
    
    logger.debug(f"Resume ID: {resume_id}")
    logger.debug(f"Window Closed Time: {window_closed_time}")
    
    if resume_id == -1:
        resume_id = part_id
    else:
        if window_closed_time is not None:
            current_time = timezone.now()
            time_difference = current_time - window_closed_time
            logger.debug(f"Time Difference: {time_difference.total_seconds()}")
    
    logger.debug(f"Resume ID: {resume_id}")
    logger.debug(f"Window Closed Time: {window_closed_time}")
    logger.debug(f"Current Time: {current_time}")
    logger.debug(f"Time Difference: {time_difference}")
    logger.debug(f"Part ID: {part_id}")
    logger.debug(f"Introduction ID: {introduction_id}")
    
    return resume_id, time_difference, give_reattempt, window_closed_time


# def check_course_completion(user, course):

class CounselorEnrolledCourseView(View):
    template_name = 'counselor-enrolled-course.html'
    def post(self, request, *args, **kwargs):        
        print("Post request")
        
        # Safely get and parse part_id
        try:
            part_id_list = request.POST.getlist('part_id')
            if not part_id_list:
                return JsonResponse({'success': False, 'message': 'Part ID is required'}, status=400)
            part_id = int(part_id_list[0])
        except (ValueError, IndexError, TypeError) as e:
            logger.error(f"Error parsing part_id: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Invalid part ID'}, status=400)
        
        print("Part ID: ", part_id)
        
        # Safely get and parse found dictionary
        found = {}
        found_str = request.POST.get('found', '{}')
        if found_str and found_str.strip():
            try:
                # Try ast.literal_eval first (for Python dict syntax)
                found = ast.literal_eval(found_str)
                if not isinstance(found, dict):
                    found = {}
            except (ValueError, SyntaxError) as e:
                # Fallback to JSON parsing if ast.literal_eval fails
                try:
                    found = json.loads(found_str)
                    if not isinstance(found, dict):
                        found = {}
                except (ValueError, json.JSONDecodeError):
                    logger.warning(f"Error parsing 'found' parameter: {str(e)}, using empty dict")
                    found = {}
        
        # Safely get and parse show_part_id
        try:
            show_part_id_str = request.POST.get('show_part_id', '0')
            if isinstance(show_part_id_str, list):
                show_part_id_str = show_part_id_str[0] if show_part_id_str else '0'
            show_part_id = int(show_part_id_str)
        except (ValueError, TypeError, IndexError) as e:
            logger.warning(f"Error parsing show_part_id: {str(e)}, using 0")
            show_part_id = 0
        
        # Safely get and parse introduction_id list
        introduction_id = []
        introduction_id_list = request.POST.getlist('introduction_id')
        if introduction_id_list and introduction_id_list[0]:
            try:
                # Try ast.literal_eval first (for Python list syntax)
                introduction_id = ast.literal_eval(introduction_id_list[0])
                if not isinstance(introduction_id, list):
                    introduction_id = []
            except (ValueError, SyntaxError, IndexError) as e:
                # Fallback to JSON parsing if ast.literal_eval fails
                try:
                    introduction_id = json.loads(introduction_id_list[0])
                    if not isinstance(introduction_id, list):
                        introduction_id = []
                except (ValueError, json.JSONDecodeError, IndexError):
                    logger.warning(f"Error parsing 'introduction_id' parameter: {str(e)}, using empty list")
                    introduction_id = []
        
        course_name = request.POST.get('course_name', '')
        if not course_name:
            return JsonResponse({'success': False, 'message': 'Course name is required'}, status=400)
        results = {}
        # Ensure part_id is being processed correctly
        part = get_object_or_404(Part, id=part_id)
        results[part.id] = {'quiz_results': [], 'correct_count': 0, 'incorrect_count': 0}
        for quiz in part.quizzes.all():
            total_questions_each_quiz = quiz.questions.count()
            correct_answers_map = {}
            for question in quiz.questions.all():
                user_answer_id = request.POST.get(f'question_{question.id}')
                user_answer = None
                if user_answer_id:
                    try:
                        user_answer = QuizAnswers.objects.get(id=user_answer_id)
                    except QuizAnswers.DoesNotExist:
                        pass
                correct_answer = question.answers.filter(is_correct=True).first()
                is_correct = user_answer == correct_answer if user_answer else False
                if is_correct:
                    results[part.id]['correct_count'] += 1
                else:
                    results[part.id]['incorrect_count'] += 1
                # Fill correct_option based on user and correct answers
                correct_answers_map[f'ques_{question.id}'] = {
                    'correct_ans': correct_answer.answer_text if correct_answer else None,
                    'selected_ans': user_answer.answer_text if user_answer else None,
                }
            # print("correct_answers_map",correct_answers_map)
            results[part.id]['quiz_results'].append({
                'quiz_id': quiz.id,
                'total_questions_in_quiz': total_questions_each_quiz,
                'correct_option': correct_answers_map,
                'quiz_result': {
                    'correct_answers': results[part.id]['correct_count'],
                    'incorrect_answers': results[part.id]['incorrect_count'],
                }
            })
        print(results)
        # Prepare final data structure
        data = {
            "userId": request.session.get('id'),
            "scores": []
        }
        for part_id, part_results in results.items():
            for quiz in part_results['quiz_results']:
                score_info = {
                    "part_id": part_id,
                    "quiz_id": quiz["quiz_id"],
                    "total_questions_in_quiz": quiz["total_questions_in_quiz"],
                    "correct_option": quiz["correct_option"],
                    "quiz_result": {
                        "correct_answers": quiz['quiz_result']['correct_answers'],
                        "incorrect_answers": quiz['quiz_result']['incorrect_answers'],
                    },
                }
                data['scores'].append(score_info)  
        user = get_object_or_404(CounselorUser, id=data['userId'])
        course=get_object_or_404(CounselorCourse, title=course_name)
        quiz_results, created = QuizResults.objects.update_or_create(user=user,course=course)
        if isinstance(quiz_results.scores, str) or not isinstance(quiz_results.scores, list):
            quiz_results.scores = []
        for new_score in data["scores"]:
            part_id = new_score["part_id"]
            quiz_id = new_score["quiz_id"]
            existing_score = next((score for score in quiz_results.scores if score["part_id"] == part_id and score["quiz_id"] == quiz_id), None)
            if existing_score:
                existing_score.update(new_score)
                messages.success(request, "Thank you! Successfully updated data into db.")
            else:
                quiz_results.scores.append(new_score)
                messages.success(request, "Thank you! Successfully created data into db.")
        # Save the updated data
        quiz_results.save()
        url = request.META.get('HTTP_REFERER')
        print("URL: ",url)

        score_pass = 0
        score_percent = int((quiz['quiz_result']['correct_answers']/quiz["total_questions_in_quiz"])*100)
        if score_percent >= 60:
            score_pass = 1
        
        # Handle attempt logic
        if score_pass == 1:
            # Passed: delete entry if exists
            UserQuizAttemptTrack.objects.filter(user=user, course=course, part=part).delete()
        else:
            # Not passed
            try:
                attempt = UserQuizAttemptTrack.objects.get(user=user, course=course, part=part)
                if attempt.no_of_attempt == 1:
                    attempt.no_of_attempt = 2
                    attempt.window_closed_time = timezone.now()
                elif attempt.no_of_attempt == 2:
                    attempt.no_of_attempt = 3
                attempt.save()
            except UserQuizAttemptTrack.DoesNotExist:
                # First attempt
                UserQuizAttemptTrack.objects.create(user=user, course=course, part=part, no_of_attempt=1)
        print("Post request 2")
        print("Found: ",found)
        print("Introduction ID: ",introduction_id)
        print("show_part_id: ",type(show_part_id))
        resume_id , time_difference , no_of_attempt, window_closed_time= show_reattempt_or_not(user,course,show_part_id,found,introduction_id)
        response_data = {
        'scores': data['scores'],
        'no_of_attempt': no_of_attempt,
        'time_difference': time_difference.total_seconds() if time_difference else None,
        'window_closed_time': window_closed_time.isoformat() if window_closed_time else None,
        'success': True
        }
    
        return JsonResponse(response_data)
        # return HttpResponseRedirect(url)
    
    def get(self, request, *args, **kwargs):
        # Extract course_name from kwargs (URL parameter)
        course_name = kwargs.get('course_name')
        if not course_name:
            # If no course_name in URL, try to get from session or redirect
            return redirect('counselor:icef_view')
        course_with_related_data=''
        course_title=''
        certificate_grant=''
        user_name=''
        grade=''
        scores = []
        found = {}
        answers_data = {} 
        part_scores = []
        correct_answers = []
        incorrect_answers = []
        user_progress=[]
        introduction_id=[]
        resume_chapter_id=None
        total_parts=0
        print("Get request")
        if not request.session.get('id'):
            return redirect('counselor:login_view')
        
        user_id = request.session.get('id')
        # OPTIMIZATION: Use select_related and only() to reduce queries
        course = CounselorCourse.objects.only('id', 'title').get(title=course_name)
        # OPTIMIZATION: Use get() with only() instead of filter().first()
        counselor_user = CounselorUser.objects.only('id', 'username').get(id=user_id)
        user_name = counselor_user.username
        # Prefetch parts, their quizzes, questions, and answers
        course_with_related_data = get_course_with_related_data(course_name)
        total_parts, part_ids, user_progress, scores, found, answers_data, part_scores, correct_answers, incorrect_answers, complete_status, introduction_id,user_progress_quiz = getUserProgress(user_id,course_with_related_data,course_name)
    
        course_title=''
        if course_name=='UK':
            course_title='UK Agent and Counsellor Training Course'
        elif course_name=='Germany':
            course_title='Germany Agent and Counsellor Training Course'

        ####################User progress Status########################
        print("User Progress Quiz: ", user_progress_quiz)
        # print("User progress: ",user_progress)
        # print(len(introduction_id))
        
        # print("Total Parts: ",total_parts)

        # completed_parts=list(set(part_ids) & set(user_progress))
        # number_of_completed_parts= len(list(set(completed_parts) - set(introduction_id)))

        
        #################### To grant certificate ####################
        grade=''
        issued_date=''
        certificate_code=''
        certificate_grant=False
        total_questions_in_course = 0
        correct_questions_of_user_for_course = 0
        # OPTIMIZATION: Reuse counselor_user instead of querying again
        user = counselor_user
        total_parts=total_parts-len(introduction_id)
        number_of_completed_parts= len(user_progress_quiz)
        completed_percent_value = int((number_of_completed_parts/total_parts)*100)
        print("Correct answers: ",correct_answers)
        print("Incorrect answers: ",incorrect_answers)
        print("Length of correct answers: ",len(correct_answers))
        print("Length of incorrect answers: ",len(incorrect_answers))

        # OPTIMIZATION: Use select_related to avoid extra query
        try:
            certificate = CounselorCertification.objects.select_related('user', 'course').get(user=user, course=course)
        except CounselorCertification.DoesNotExist:
            certificate = None
        if certificate:
            certificate_grant=True
            grade=certificate.grade
            issued_date=certificate.created_at.strftime('%d-%m-%Y')
            certificate_code=certificate.certificate_code

        elif total_parts == number_of_completed_parts:
            # OPTIMIZATION: Use only() to reduce data fetched (don't need related objects)
            try:
                quiz_result = QuizResults.objects.only('scores', 'user_id', 'course_id').get(user_id=user, course=course)
            except QuizResults.DoesNotExist:
                quiz_result = None
            print("Quiz result: ",quiz_result)

            if quiz_result:
                if quiz_result.scores:
                    quiz_scores = quiz_result.scores
                    print("Quiz scores: ",quiz_scores)
                    for score in quiz_scores:
                        score_percent = int((score['quiz_result']['correct_answers']/score["total_questions_in_quiz"])*100)
                        total_questions_in_course = total_questions_in_course + score['total_questions_in_quiz']
                        if score_percent >= 60:
                            correct_questions_of_user_for_course = correct_questions_of_user_for_course + score['quiz_result']['correct_answers']
            
            total_percent = int((correct_questions_of_user_for_course/total_questions_in_course)*100)
            print("Total percent: ",total_percent)
            if total_percent > 90:
                grade = 'A+'
            elif total_percent > 80:
                grade = 'A'
            elif total_percent > 70:
                grade = 'B+'
            elif total_percent > 60:
                grade = 'B'
            else:
                grade = 'C'
            
            certificate = CounselorCertification.objects.create(user=user,course=course,grade=grade)
            certificate.save()
            certificate_code=certificate.certificate_code
            issued_date=certificate.created_at.strftime('%d-%m-%Y')

            certificate_grant=True
        
        
        # if False in found.values() or len(found) == 0:
        #     certificate_grant=False
        # else:
        #     certificate_grant=True
        #############################################################

        ############### To Resume test #######################
        # print('Introduction ID: ',introduction_id)
        show_part_id=''
        show_quiz_id=None
        # OPTIMIZATION: Cache first_part_id to avoid repeated queries
        # Note: Use Python sorting since parts are already prefetched
        first_chapter = None
        chapters_list = list(course_with_related_data.chapters.all())
        if chapters_list:
            # Sort chapters by index (already in memory from prefetch)
            chapters_list.sort(key=lambda c: c.index)
            first_chapter = chapters_list[0]
        
        first_part = None
        if first_chapter and first_chapter.parts.exists():
            parts_list = list(first_chapter.parts.all())
            if parts_list:
                # Sort parts by index (already in memory from prefetch)
                parts_list.sort(key=lambda p: p.index)
                first_part = parts_list[0]
        
        first_part_id = first_part.id if first_part else None
        
        print("Found: ",(found))
        if len(found)==0:
            show_part_id = first_part_id if first_part_id else ''
        else:
            for key, value in found.items():
                if value == False and not(key in introduction_id):
                    show_part_id=key
                    break
        
        
        # OPTIMIZATION: Combine queries and use select_related
        part_obj = None
        if show_part_id != '':
            # OPTIMIZATION: Use select_related to avoid extra query for chapter
            # Note: Don't use .only() when we need to access chapter relationship
            part_obj = Part.objects.select_related('chapter').get(id=show_part_id)
            obj, created = UserProgressTrack.objects.update_or_create(
                user=user, 
                course=course,
                defaults={
                    'resume_part': part_obj
                }
            )
            resume_chapter_id = part_obj.chapter.id
            
            # OPTIMIZATION: Check progress in same block
            if CourseContentProgress.objects.filter(user=user, part_id=show_part_id).exists():
                # Check if quiz is completed (has results saved)
                if show_part_id in found and found[show_part_id]:
                    # Quiz is completed - show results
                    show_quiz_id = show_part_id
                else:
                    # Part completed but quiz not taken - show quiz form
                    show_quiz_id = show_part_id
        
        if show_part_id == '' and show_quiz_id is None:
            show_part_id = first_part_id if first_part_id else ''

        # OPTIMIZATION: Reuse part_obj if available, otherwise fetch once
        if show_part_id and show_part_id != '':
            try:
                if part_obj and part_obj.id == show_part_id:
                    part_content_testing = part_obj
                else:
                    part_content_testing = Part.objects.only('id', 'title', 'description').get(id=show_part_id)
                
                # OPTIMIZATION: Single query with prefetch_related
                quiz_content_testing = Part.objects.prefetch_related(
                    'quizzes__questions__answers'
                ).only('id').filter(
                    id=show_part_id
                ).first()
            except Part.DoesNotExist:
                part_content_testing = None
                quiz_content_testing = None
        else:
            part_content_testing = None
            quiz_content_testing = None

        if show_quiz_id is None:
            show_quiz_id=-1

        # NEW: Check if quiz is completed (has results saved) for the current part
        quiz_completed = False
        if show_part_id and show_part_id != '':
            if show_part_id in found and found[show_part_id]:
                # Quiz has results, so it's completed
                quiz_completed = True
        
        resume_id , time_difference , no_of_attempt, window_closed_time= show_reattempt_or_not(user,course,show_part_id,found,introduction_id)
        if resume_id != show_part_id:
            show_part_id = resume_id
            show_quiz_id = resume_id
            # Re-check quiz completion status after resume_id update
            if show_part_id and show_part_id != '':
                if show_part_id in found and found[show_part_id]:
                    quiz_completed = True
                    # If quiz is completed, show results
                    show_quiz_id = show_part_id
            
        print("No of attempt : ", no_of_attempt)
        print("Show part id: ",show_part_id)
        print("Show quiz id: ",show_quiz_id)
        print("Quiz completed: ",quiz_completed)
    
        # show_part_id = next(iter(found))
        # Check if autocomplete is enabled for this course
        autocomplete_enabled = request.session.get(f'autocomplete_{course_name}', False)
        
        # OPTIMIZATION: Cache all_parts_ordered to avoid repeated iterations
        # Get next part after current part
        next_part = None
        # Use already prefetched data - no additional queries needed
        all_parts_ordered = []
        # Build list with chapter index for sorting
        for chapter in course_with_related_data.chapters.all():
            chapter_index = chapter.index  # Get index from prefetched chapter
            for part in chapter.parts.all():
                # Store tuple with (chapter_index, part_index, part) for sorting
                all_parts_ordered.append((chapter_index, part.index, part))
        # Sort by chapter index, then part index
        all_parts_ordered.sort(key=lambda x: (x[0], x[1]))
        # Extract just the parts after sorting
        all_parts_ordered = [part for _, _, part in all_parts_ordered]
        
        current_part_index = None
        for idx, part in enumerate(all_parts_ordered):
            if part.id == show_part_id:
                current_part_index = idx
                break
        
        if current_part_index is not None and current_part_index < len(all_parts_ordered) - 1:
            next_part = all_parts_ordered[current_part_index + 1]
        
        if resume_chapter_id is None:
            resume_chapter_id=course_with_related_data.chapters.all()[0].id
        
        # NEW: Get next part for completed quiz "Next" button
        next_part_for_quiz = None
        if quiz_completed and show_quiz_id == show_part_id and show_quiz_id != -1:
            # If quiz is completed, use the same next_part
            next_part_for_quiz = next_part
        
        # NEW: Calculate quiz pass/fail status for all parts with quiz results
        quiz_pass_status = {}  # Dictionary to store pass status for each part
        has_passed_quiz_status = {}  # Dictionary to store if user has passed (attempt track deleted)
        
        # Calculate pass status for all parts that have quiz results
        for part_id, answer_data in answers_data.items():
            correct_count = answer_data.get('correct', 0)
            incorrect_count = answer_data.get('incorrect', 0)
            total_questions = correct_count + incorrect_count
            if total_questions > 0:
                score_percent = int((correct_count / total_questions) * 100)
                quiz_pass_status[part_id] = score_percent >= 60
        
        # NEW: Check if user has passed quiz for all parts (UserQuizAttemptTrack deleted = passed)
        # OPTIMIZATION: Fetch all attempt tracks in one query
        attempt_tracks = UserQuizAttemptTrack.objects.filter(
            user=user, 
            course=course
        ).values_list('part_id', flat=True)
        attempt_track_part_ids = set(attempt_tracks)
        
        # For each part with quiz results, check if attempt track exists
        for part_id in answers_data.keys():
            # If attempt track doesn't exist for this part, user has passed (it was deleted on pass)
            has_passed_quiz_status[part_id] = part_id not in attempt_track_part_ids
        
        # Determine which buttons to show for current quiz:
        # Case 1: Failed quiz (not passed) → only "Re-attempt" button
        # Case 2: Failed first, passed later → show final pass result, only "Next" button
        # Case 3: Passed first attempt → only "Next" button
        show_next_button = False
        show_reattempt_button = False
        current_quiz_part_id = None
        
        # Convert show_quiz_id and show_part_id to int for comparison
        try:
            current_quiz_part_id = int(show_quiz_id) if show_quiz_id and show_quiz_id != -1 else None
            current_part_id_int = int(show_part_id) if show_part_id and show_part_id != '' else None
        except (ValueError, TypeError):
            current_quiz_part_id = None
            current_part_id_int = None
        
        if quiz_completed and current_quiz_part_id and current_quiz_part_id == current_part_id_int:
            # Check if user has passed this quiz
            has_passed = has_passed_quiz_status.get(current_quiz_part_id, False)
            if has_passed:
                # User has passed (either first attempt or later attempt) → show only "Next"
                show_next_button = True
                show_reattempt_button = False
            else:
                # User hasn't passed yet → show only "Re-attempt"
                show_next_button = False
                show_reattempt_button = True
        
        context = {
            'course': course_with_related_data,
            'scores':scores,
            'found' : found,
            'answers_data': answers_data,
            'part_scores': part_scores,
            'correct_answers':correct_answers,
            'incorrect_answers':incorrect_answers,
            'complete_status':user_progress,
            'course_title':course_title,
            'certificate_grant':certificate_grant,
            'issued_date':issued_date,
            'certificate_code':certificate_code,
            'grade':grade,     
            'user_name':user_name,
            'show_part_id':show_part_id,
            'show_quiz_id':show_quiz_id,
            'resume_chapter_id':resume_chapter_id,
            'total_parts':total_parts,
            'number_of_completed_parts':number_of_completed_parts,
            'completed_percent_value':completed_percent_value,
            'part_content_testing':part_content_testing,
            'quiz_content_testing':quiz_content_testing,
            'no_of_attempt':no_of_attempt,
            'time_difference':time_difference,
            'window_closed_time':window_closed_time,
            'introduction_id':introduction_id,
            'autocomplete_enabled': autocomplete_enabled,
            'course_name': course_name,
            'next_part': next_part,
            'quiz_completed': quiz_completed,  # NEW: Add quiz completion status
            'next_part_for_quiz': next_part_for_quiz,  # NEW: Next part when viewing completed quiz
            'quiz_pass_status': quiz_pass_status,  # NEW: Pass status for all parts (dict: part_id -> bool)
            'has_passed_quiz_status': has_passed_quiz_status,  # NEW: Whether user has passed for each part (dict: part_id -> bool)
            'show_next_button': show_next_button,  # NEW: Whether to show Next button for current quiz
            'show_reattempt_button': show_reattempt_button,  # NEW: Whether to show Re-attempt button for current quiz
            'debug': settings.DEBUG,  # NEW: Debug flag for console logging
        }
        found = dict(found)
        

        return render(request, self.template_name, context)


def quiz_autocomplete(request, course_name):
    """
    Autocomplete functionality activation - sets session flag for course.
    Requires master password authentication.
    URL: /fetch_current_part/<course_name>/autocomplete/
    """
    # Check if user is logged in
    if not request.session.get('id'):
        messages.error(request, "Please login first.")
        return redirect('counselor:login_view')
    
    user = get_object_or_404(CounselorUser, id=request.session.get('id'))
    course = get_object_or_404(CounselorCourse, title=course_name)
    
    # Handle POST request (password submission)
    if request.method == 'POST':
        master_password = request.POST.get('master_password', '')
        correct_password = settings.MASTER_PASSWORD
        
        if master_password != correct_password:
            messages.error(request, "Invalid master password. Please try again.")
            return render(request, 'quiz-autocomplete.html', {
                'course_name': course_name,
                'course': course,
            })
        
        # Password is correct, set session flag for this course
        session_key = f'autocomplete_{course_name}'
        request.session[session_key] = True
        request.session.modified = True
        
        messages.success(
            request, 
            f"Autocomplete mode activated for course '{course_name}'. You can now use the autocomplete button on quiz pages."
        )
        # Redirect to course overview or first part
        return redirect('counselor:counselor_enrolled_course_param', course_name=course_name)
    
    # GET request - show password form
    return render(request, 'quiz-autocomplete.html', {
        'course_name': course_name,
        'course': course,
    })


def course_autocomplete(request, course_name):
    """
    Full course autocomplete functionality - marks all parts as complete and completes all quizzes.
    Requires master password authentication.
    URL: /counselor_enrolled_course/<course_name>/autocomplete-full/
    """
    # Check if user is logged in
    if not request.session.get('id'):
        messages.error(request, "Please login first.")
        return redirect('counselor:login_view')
    
    user = get_object_or_404(CounselorUser, id=request.session.get('id'))
    course = get_object_or_404(CounselorCourse, title=course_name)
    
    # Handle POST request (password submission and autocomplete execution)
    if request.method == 'POST':
        master_password = request.POST.get('master_password', '')
        correct_password = settings.MASTER_PASSWORD
        
        if master_password != correct_password:
            messages.error(request, "Invalid master password. Please try again.")
            return render(request, 'course-autocomplete.html', {
                'course_name': course_name,
                'course': course,
            })
        
        # Password is correct, proceed with full course autocomplete
        try:
            with transaction.atomic():
                # Get all parts in the course
                all_parts = []
                for chapter in course.chapters.all():
                    all_parts.extend(chapter.parts.all())
                
                parts_completed = 0
                quizzes_completed = 0
                
                # Mark all parts as complete
                for part in all_parts:
                    CourseContentProgress.objects.update_or_create(
                        user=user,
                        part_id=part,
                        defaults={'completed': True}
                    )
                    parts_completed += 1
                    
                    # Complete all quizzes for each part
                    if part.quizzes.exists():
                        for quiz in part.quizzes.all():
                            # Calculate total questions and create perfect score
                            total_questions = quiz.questions.count()
                            if total_questions > 0:
                                # Create correct_option map with all correct answers
                                correct_answers_map = {}
                                for question in quiz.questions.all():
                                    correct_answer = question.answers.filter(is_correct=True).first()
                                    if correct_answer:
                                        correct_answers_map[f'ques_{question.id}'] = {
                                            'correct_ans': correct_answer.answer_text,
                                            'selected_ans': correct_answer.answer_text,  # User selected correct answer
                                        }
                                
                                # Create score entry in the same format as regular quiz submissions
                                score_data = {
                                    'quiz_id': quiz.id,
                                    'total_questions_in_quiz': total_questions,
                                    'correct_option': correct_answers_map,
                                    'quiz_result': {
                                        'correct_answers': total_questions,
                                        'incorrect_answers': 0,
                                    },
                                    'part_id': part.id
                                }
                                
                                # Get or create QuizResults for this user and course
                                quiz_result, created = QuizResults.objects.get_or_create(
                                    user=user,
                                    course=course,
                                    defaults={'scores': []}
                                )
                                
                                # Ensure scores is a list
                                if not isinstance(quiz_result.scores, list):
                                    quiz_result.scores = []
                                
                                # Check if score for this quiz already exists
                                existing_score_index = None
                                for idx, score in enumerate(quiz_result.scores):
                                    if isinstance(score, dict) and score.get('quiz_id') == quiz.id:
                                        existing_score_index = idx
                                        break
                                
                                if existing_score_index is not None:
                                    # Update existing score
                                    quiz_result.scores[existing_score_index] = score_data
                                else:
                                    # Add new score
                                    quiz_result.scores.append(score_data)
                                
                                quiz_result.save()
                                
                                # Delete UserQuizAttemptTrack to mark quiz as passed
                                UserQuizAttemptTrack.objects.filter(
                                    user=user,
                                    course=course,
                                    part=part
                                ).delete()
                                
                                quizzes_completed += 1
                
                # Set session flag for full course autocomplete
                session_key = f'course_autocomplete_{course_name}'
                request.session[session_key] = True
                request.session.modified = True
                
                messages.success(
                    request,
                    f"Full course autocomplete completed for '{course_name}'. "
                    f"Marked {parts_completed} parts as complete and completed {quizzes_completed} quizzes."
                )
                
                logger.info(
                    f"Full course autocomplete: User {user.id} completed course {course_name} "
                    f"({parts_completed} parts, {quizzes_completed} quizzes)"
                )
        
        except Exception as e:
            logger.error(f"Error during full course autocomplete: {str(e)}")
            messages.error(
                request,
                f"An error occurred during autocomplete: {str(e)}. Please try again."
            )
            return render(request, 'course-autocomplete.html', {
                'course_name': course_name,
                'course': course,
            })
        
        # Redirect to course page
        return redirect('counselor:counselor_enrolled_course_param', course_name=course_name)
    
    # GET request - show password form
    return render(request, 'course-autocomplete.html', {
        'course_name': course_name,
        'course': course,
    })