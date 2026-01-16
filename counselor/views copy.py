from django.db import IntegrityError
from django.shortcuts import render
from datetime import datetime, date, timedelta
import json
from django.conf import settings
from django.contrib import messages
from django.shortcuts import render
from .models import CounselorUser, CourseOverviewSummary, Quiz, Chapter, Part, QuizAnswers, QuizResults ,CourseContentProgress, CounselorCourse, UserProgressTrack
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
User = get_user_model()

#New commented code

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
    return render(request, 'icef-course.html')

def learn_more_view_uk(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'uk-counsellor-course.html')

def learn_more_view_germany(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'germany-counsellor-course.html')

def learn_more_view_usa(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'usa-counsellor-course.html')

def learn_more_view_canada(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'canada-counsellor-course.html')

def learn_more_view_nz(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'nz-counsellor-course.html')

def learn_more_view_australia(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'australia-counsellor-course.html')

def learn_more_view_dubai(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'dubai-counsellor-course.html')

def learn_more_view_ireland(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'ireland-counsellor-course.html')

def learn_more_view_france(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'france-counsellor-course.html')

def learn_more_view_singapore(request):
    if not request.session.get('id'):
        return redirect('counselor:login_view')
    return render(request,'singapore-counsellor-course.html')

@csrf_exempt
def update_part_status(request, part_id):
    if not request.session.get('id'):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)
    user_id=request.session.get('id')
    Counselor_user = CounselorUser.objects.get(id=user_id)
    part=Part.objects.get(id=part_id)
    CourseContentProgress.objects.update_or_create(user=Counselor_user, part_id=part, defaults={'completed': True})
    return JsonResponse({'success': True, 'message': 'Part marked as complete'})

def user_login(request):
    if request.method == "POST":
        username = request.POST.get('Username')
        password = request.POST.get('password')
        try:
            user = CounselorUser.objects.get(email=username)
            if user.password == password:  # Use Django's password hashing in production
                # print(user.id)    
                request.session['id'] = user.id
                messages.success(request, "Login successful!")
                return redirect('counselor:icef_view')  # Replace 'home' with the desired URL name
            else:
                messages.error(request, "Incorrect password.")
        except CounselorUser.DoesNotExist:
            messages.error(request, "Username not found.")
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

def course_overview(request,course_name):
    course_overview_with_related_data=[]
    intro=''
    conclusion=''
    resume=0
    try:
        # Prefetch parts, their quizzes, questions, and answers
        course_overview_with_related_data = CounselorCourse.objects.prefetch_related(
        'chapters__points'
    ).filter(
        title=course_name
    ).first()
        summaries = CourseOverviewSummary.objects.filter(course__title='UK').values('title1', 'title2')
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
    
    
    context={
        'course': course_overview_with_related_data,
        'image_name': 'ukcourse',
        'intro': intro,
        'conclusion': conclusion,
        'resume': resume,
    }
    return render(request, 'course-overview.html', context)

def get_course_with_related_data(course_name):
    course_with_related_data = []
    try:
        # Prefetch parts, their quizzes, questions, and answers
        course_with_related_data = CounselorCourse.objects.prefetch_related(
        'chapters__parts__quizzes__questions__answers'
    ).filter(
        title=course_name
    ).first()
        
    except Chapter.DoesNotExist:
        course_with_related_data = []
    return course_with_related_data

def getUserProgress(course_with_related_data):
    total_parts = sum(chapter.parts.count() for chapter in course_with_related_data.chapters.all())
    print("Total parts: ", total_parts)

    part_ids = [part.id for chapter in course_with_related_data.chapters.all() for part in chapter.parts.all()]
    print("Part ids: ",part_ids)

    total_parts=len(part_ids)
    print("Total parts: ", total_parts)

    return total_parts,part_ids

# def getUserProgress():
#     introduction_id=[]
#     total_parts=total_parts-len(introduction_id)
#     completed_parts=list(set(part_ids) & set(user_progress))
#     number_of_completed_parts= len(list(set(completed_parts) - set(introduction_id)))
#     completed_percent_value = int((number_of_completed_parts/total_parts)*100)

    
class CounselorEnrolledCourseView(View):
    template_name = 'counselor-enrolled-course.html'
    def post(self, request, *args, **kwargs):        
        print("Post")
        course_name=request.POST.get('course_name')
        results = {}
        # Ensure part_id is being processed correctly
        for part_id in request.POST.getlist('part_id'):
        
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
        return HttpResponseRedirect(url)
    
    def get(self, request,course_name):
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
        
        # Prefetch parts, their quizzes, questions, and answers
        course_with_related_data = get_course_with_related_data(course_name)
        total_parts , part_ids = getUserProgress(course_with_related_data)
        
        user_progress=''
        user_name=''

        try:
            user = request.session.get('id')  # Get user ID from session
            user_name = CounselorUser.objects.filter(id=user).first().username
            user_progress = list(CourseContentProgress.objects.filter(user=user).values_list('part_id', flat=True))
            # print(user_progress)
            course=get_object_or_404(CounselorCourse, title=course_name)
            quiz_result = QuizResults.objects.get(user_id=user,course=course)
            scores = quiz_result.scores if isinstance(quiz_result.scores, list) else []
                       
            # Initialize counters
            total_questions = 0
            total_correct_answers = 0
            # Iterate through each quiz result
            for quiz in scores:
                total_questions += quiz["total_questions_in_quiz"]
                total_correct_answers += quiz["quiz_result"]["correct_answers"]
            # Calculate score percentage
            if total_questions > 0:
                score_percentage = (total_correct_answers / total_questions) * 100
            else:
                score_percentage = 0
            # Determine the grade based on the score percentage
            if score_percentage >= 80:
                grade = "A+"
            elif score_percentage >= 70:
                grade = "A"
            elif score_percentage >= 60:
                grade = "B+"
            elif score_percentage >= 50:
                grade = "B"
            elif score_percentage >= 40:
                grade = "C"
            else:
                grade = "D"  # Fail or below 50%

            # Output the results
            print(f"Total Number of Questions: {total_questions}")
            print(f"Total Number of Correct Answers: {total_correct_answers}")
            print(f"Score Percentage: {score_percentage:.2f}%")
            print(f"Grade: {grade}")
            found = {}
            answers_data = {}  # To store correct and incorrect counts for each part
            correct_selected = {}

            print("First Part ID: ",course_with_related_data.chapters.all()[0].parts.all()[0].id)
            for chapter in course_with_related_data.chapters.all():
                for part in chapter.parts.all():
                    if part.title == 'Introduction':
                        introduction_id.append(part.id)
                    part_scores = [score for score in scores if score.get('part_id') == part.id]
                    # print("part_scores",part_scores)
                    # Extract correct and incorrect counts from the scores
                    correct_count = sum(score['quiz_result']['correct_answers'] for score in part_scores)
                    incorrect_count = sum(score['quiz_result']['incorrect_answers'] for score in part_scores)
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
                    # Loop through the scores
                    for quiz in scores:
                        part_id = quiz['part_id']
                        for question_key, question_data in quiz['correct_option'].items():
                            correct_answer = question_data['correct_ans']
                            selected_answer = question_data['selected_ans']
                            correct_selected[part.id] = {
                                'correct_answer': correct_answer,
                                'selected_answer': selected_answer
                            }
                            # Print the details
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
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            scores = []
            found = {}
            answers_data = {}
            part_scores = []
            correct_answers = []
            incorrect_answers = []
            complete_status=[]
        course_title=''
        if course_name=='UK':
            course_title='UK Agent and Counsellor Training Course'
        elif course_name=='Germany':
            course_title='Germany Agent and Counsellor Training Course'

####################User progress Status########################
        print("User progress: ",user_progress)
        total_parts=total_parts-len(introduction_id)
        completed_parts=list(set(part_ids) & set(user_progress))
        number_of_completed_parts= len(list(set(completed_parts) - set(introduction_id)))
        completed_percent_value = int((number_of_completed_parts/total_parts)*100)
#################### To grant certificate #################### 
        certificate_grant=True
        # if False in found.values() or len(found) == 0:
        #     certificate_grant=False
        # else:
        #     certificate_grant=True
#############################################################

############### To Resume test #######################
        print('Introduction ID: ',introduction_id)
        show_part_id=''
        first_part_id=course_with_related_data.chapters.all()[0].parts.all()[0].id
        if len(found)==0:
            show_part_id=first_part_id
        else:
            for key, value in found.items():
                if value == False and not(key in introduction_id):
                    show_part_id=key
                    break
        user = CounselorUser.objects.get(id=request.session.get('id'))
        part = Part.objects.get(id=show_part_id)
        course = CounselorCourse.objects.get(title=course_name)
        obj, created = UserProgressTrack.objects.update_or_create(
            user=user, 
            course=course,
            defaults={
                'resume_part': part
            }
        )
#############################################################

        # show_part_id = next(iter(found))
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
            'grade':grade,
            'show_part_id':show_part_id,
            'resume_chapter_id':resume_chapter_id,
            'total_parts':total_parts,
            'number_of_completed_parts':number_of_completed_parts,
            'completed_percent_value':completed_percent_value,
        }

        print('resume_chapter_id: ',resume_chapter_id)
        print("user Name: ",user_name)
        found = dict(found)
        print(type(found))
        print(get(found, 2))
        print("part_scores",part_scores)
        print("Found", found)
        print('Certificate Granted: ',certificate_grant)

        return render(request, self.template_name, context)


from django.http import JsonResponse
import json
import traceback
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
