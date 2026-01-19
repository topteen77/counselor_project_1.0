"""
Production-ready views for Counselor Training Platform
Following COURSE_FLOW_DOCUMENTATION.md specifications
"""

import ast
import json
import logging
from datetime import timedelta
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Prefetch
from django.contrib import messages
from django.conf import settings

from .models import (
    CounselorCertification, CounselorUser, CourseOverviewSummary,
    Question, Quiz, Chapter, Part, QuizAnswers, QuizResults,
    CourseContentProgress, CounselorCourse, UserProgressTrack,
    UserQuizAttemptTrack
)

logger = logging.getLogger(__name__)


# ============================================================================
# SERVICE CLASSES - Business Logic Separation
# ============================================================================

class CourseDataService:
    """Service for fetching and managing course data with optimizations"""
    
    @staticmethod
    def get_course_with_related_data(course_name):
        """Fetch course with all related data using optimized prefetch"""
        try:
            return CounselorCourse.objects.prefetch_related(
                Prefetch(
                    'chapters',
                    queryset=Chapter.objects.order_by('index')
                ),
                Prefetch(
                    'chapters__parts',
                    queryset=Part.objects.only('id', 'title', 'index', 'chapter_id', 'description')
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
            ).only('id', 'title').filter(title=course_name).first()
        except Exception as e:
            logger.error(f"Error fetching course data: {str(e)}")
            return None


class UserProgressService:
    """Service for managing user progress calculations"""
    
    @staticmethod
    def get_user_progress(user, course_with_related_data, course_name):
        """
        Calculate user progress following documentation specifications
        Returns: progress_data dict with all calculated values
        """
        progress_data = {
            'total_parts': 0,
            'part_ids': [],
            'user_progress': [],
            'scores': [],
            'found': {},
            'answers_data': {},
            'part_scores': [],
            'correct_answers': [],
            'incorrect_answers': [],
            'complete_status': [],
            'introduction_id': [],
            'user_progress_quiz': {},
            'correct_selected': {},
            'parts_with_quizzes': set()  # Track which parts have quizzes
        }
        
        try:
            # Get all part IDs
            part_ids = [
                part.id 
                for chapter in course_with_related_data.chapters.all() 
                for part in chapter.parts.all()
            ]
            progress_data['total_parts'] = len(part_ids)
            progress_data['part_ids'] = part_ids
            
            # Get user's completed parts
            progress_data['user_progress'] = list(
                CourseContentProgress.objects.filter(user=user)
                .values_list('part_id', flat=True)
            )
            
            # Get quiz results
            try:
                course = CounselorCourse.objects.get(title=course_name)
                quiz_result = QuizResults.objects.only('scores', 'user_id', 'course_id').get(
                    user_id=user, course=course
                )
                if quiz_result:
                    progress_data['scores'] = (
                        quiz_result.scores 
                        if isinstance(quiz_result.scores, list) 
                        else []
                    )
            except QuizResults.DoesNotExist:
                progress_data['scores'] = []
            
            # Process each part
            for chapter in course_with_related_data.chapters.all():
                for part in chapter.parts.all():
                    # Track which parts have quizzes
                    if part.quizzes.exists():
                        progress_data['parts_with_quizzes'].add(part.id)
                    
                    # Identify Introduction parts
                    is_introduction = part.title == 'Introduction'
                    if is_introduction:
                        progress_data['introduction_id'].append(part.id)
                        # Introduction parts have no quizzes - skip all quiz processing
                        progress_data['found'][part.id] = False  # Never mark as having quiz results
                        progress_data['answers_data'][part.id] = {
                            'correct': 0,
                            'incorrect': 0
                        }
                        continue  # Skip all quiz-related processing for Introduction parts
                    
                    # Get scores for this part (only for non-Introduction parts)
                    part_scores = [
                        score for score in progress_data['scores']
                        if score.get('part_id') == part.id
                    ]
                    
                    # Track quiz IDs
                    for score in part_scores:
                        if 'quiz_id' in score:
                            progress_data['user_progress_quiz'][part.id] = score.get('quiz_id')
                    
                    # Calculate correct/incorrect counts
                    correct_count = 0
                    incorrect_count = 0
                    for score in part_scores:
                        if 'quiz_result' in score and isinstance(score['quiz_result'], dict):
                            correct_count += score['quiz_result'].get('correct_answers', 0)
                            incorrect_count += score['quiz_result'].get('incorrect_answers', 0)
                        elif 'correct_answers' in score:
                            correct_count += score.get('correct_answers', 0)
                            incorrect_count += score.get('incorrect_answers', 0)
                    
                    # Mark if quiz has results
                    progress_data['found'][part.id] = bool(part_scores)
                    
                    # Store answer data
                    progress_data['answers_data'][part.id] = {
                        'correct': correct_count,
                        'incorrect': incorrect_count
                    }
                    
                    # Process correct/incorrect answers for display
                    for quiz in part_scores:
                        if 'correct_option' in quiz and isinstance(quiz['correct_option'], dict):
                            for question_key, question_data in quiz['correct_option'].items():
                                if isinstance(question_data, dict):
                                    correct_answer = question_data.get('correct_ans')
                                    selected_answer = question_data.get('selected_ans')
                                    progress_data['correct_selected'][part.id] = {
                                        'correct_answer': correct_answer,
                                        'selected_answer': selected_answer
                                    }
                                    if selected_answer == correct_answer:
                                        progress_data['correct_answers'].append(
                                            (part.id, question_key, correct_answer, selected_answer)
                                        )
                                    else:
                                        progress_data['incorrect_answers'].append(
                                            (part.id, question_key, correct_answer, selected_answer)
                                        )
            
            # Calculate complete_status: A part is only complete if:
            # - For parts with quizzes: part content is completed AND quiz is completed
            # - For parts without quizzes: just part content is completed
            complete_status = []
            introduction_completed = []
            for part_id in progress_data['part_ids']:
                # Check if part content is completed
                content_completed = part_id in progress_data['user_progress']
                
                # Check if part has quizzes (using cached data)
                part_has_quiz = part_id in progress_data['parts_with_quizzes']
                
                # For Introduction parts (no quizzes), mark complete if content is done
                if part_id in progress_data['introduction_id']:
                    if content_completed:
                        complete_status.append(part_id)
                        introduction_completed.append(part_id)
                # For parts with quizzes, mark complete only if BOTH content and quiz are done
                elif part_has_quiz:
                    quiz_completed = progress_data['found'].get(part_id, False)
                    if content_completed and quiz_completed:
                        complete_status.append(part_id)
                # For parts without quizzes (but not Introduction), mark complete if content is done
                else:
                    if content_completed:
                        complete_status.append(part_id)
            
            progress_data['complete_status'] = complete_status
            # Debug logging for Introduction completion
            if introduction_completed:
                print(f"Introduction Parts Completed: {introduction_completed}")
            else:
                print(f"Introduction Parts Completed: None (user_progress has {len(progress_data['user_progress'])} parts)")
                # Show which Introduction parts are in user_progress
                intro_in_progress = [pid for pid in progress_data['introduction_id'] if pid in progress_data['user_progress']]
                if intro_in_progress:
                    print(f"  But Introduction parts in user_progress: {intro_in_progress}")
            
        except Exception as e:
            logger.error(f"Error calculating user progress: {str(e)}")
        
        return progress_data


class QuizAttemptService:
    """Service for managing quiz attempt tracking"""
    
    @staticmethod
    def get_reattempt_status(user, course, part_id, found, introduction_id, user_progress=None, scores=None):
        """
        Determine quiz re-attempt status following documentation
        Returns: (resume_id, time_difference, no_of_attempt, window_closed_time)
        """
        resume_id = -1
        window_closed_time = None
        time_difference = None
        no_of_attempt = 0
        
        # Check if user has any actual progress
        has_progress = False
        if user_progress and len(user_progress) > 0:
            has_progress = True
        if scores and len(scores) > 0:
            has_progress = True
        
        # If no progress at all, return the part_id (Introduction for fresh users)
        if not has_progress:
            resume_id = part_id
        elif len(found) == 0:
            resume_id = part_id
        else:
            # Prefetch all attempt tracks in single query
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
                    resume_id = attempt_track.part_id
                    
                    if attempt_track.no_of_attempt == 3:
                        no_of_attempt = 3
                        continue
                    elif attempt_track.no_of_attempt == 2:
                        window_closed_time = attempt_track.window_closed_time
                        no_of_attempt = 2
                        break
                    else:
                        no_of_attempt = 1
                        break
                elif value == False and not (key in introduction_id):
                    resume_id = key
                    break
        
        if resume_id == -1:
            resume_id = part_id
        
        if window_closed_time is not None:
            current_time = timezone.now()
            time_difference = current_time - window_closed_time
        
        return resume_id, time_difference, no_of_attempt, window_closed_time


class CertificateService:
    """Service for certificate generation and management"""
    
    @staticmethod
    def calculate_grade(total_questions, correct_questions):
        """Calculate grade based on percentage"""
        if total_questions == 0:
            return 'C'
        
        total_percent = int((correct_questions / total_questions) * 100)
        
        if total_percent > 90:
            return 'A+'
        elif total_percent > 80:
            return 'A'
        elif total_percent > 70:
            return 'B+'
        elif total_percent > 60:
            return 'B'
        else:
            return 'C'
    
    @staticmethod
    def check_and_generate_certificate(user, course, progress_data):
        """
        Check if certificate should be granted and generate if needed
        Returns: (certificate_grant, grade, issued_date, certificate_code)
        """
        try:
            # Check if certificate already exists
            try:
                certificate = CounselorCertification.objects.select_related(
                    'user', 'course'
                ).get(user=user, course=course)
                return (
                    True,
                    certificate.grade,
                    certificate.created_at.strftime('%d-%m-%Y'),
                    certificate.certificate_code
                )
            except CounselorCertification.DoesNotExist:
                pass
            
            # Calculate completion
            total_parts = progress_data['total_parts'] - len(progress_data['introduction_id'])
            number_of_completed_parts = len(progress_data['user_progress_quiz'])
            
            if total_parts == number_of_completed_parts:
                # Calculate grade from quiz scores
                total_questions = 0
                correct_questions = 0
                
                try:
                    quiz_result = QuizResults.objects.only('scores').get(
                        user_id=user, course=course
                    )
                    if quiz_result and quiz_result.scores:
                        # Exclude Introduction parts from certificate grade calculation
                        introduction_ids = progress_data.get('introduction_id', [])
                        for score in quiz_result.scores:
                            part_id = score.get('part_id')
                            # Skip Introduction parts - they have no quizzes
                            if part_id in introduction_ids:
                                continue
                            score_percent = int((
                                score['quiz_result']['correct_answers'] / 
                                score["total_questions_in_quiz"]
                            ) * 100)
                            total_questions += score['total_questions_in_quiz']
                            if score_percent >= 60:
                                correct_questions += score['quiz_result']['correct_answers']
                except QuizResults.DoesNotExist:
                    pass
                
                grade = CertificateService.calculate_grade(total_questions, correct_questions)
                certificate = CounselorCertification.objects.create(
                    user=user, course=course, grade=grade
                )
                
                return (
                    True,
                    grade,
                    certificate.created_at.strftime('%d-%m-%Y'),
                    certificate.certificate_code
                )
        
        except Exception as e:
            logger.error(f"Error checking certificate: {str(e)}")
        
        return (False, '', '', '')


class PartNavigationService:
    """Service for part navigation and ordering"""
    
    @staticmethod
    def get_ordered_parts(course_with_related_data):
        """Get all parts in correct order (by chapter index, then part index)"""
        all_parts_ordered = []
        for chapter in course_with_related_data.chapters.all():
            chapter_index = chapter.index
            for part in chapter.parts.all():
                all_parts_ordered.append((chapter_index, part.index, part))
        
        # Sort by chapter index, then part index
        all_parts_ordered.sort(key=lambda x: (x[0], x[1]))
        return [part for _, _, part in all_parts_ordered]
    
    @staticmethod
    def get_first_part(course_with_related_data):
        """Get first part of the course"""
        ordered_parts = PartNavigationService.get_ordered_parts(course_with_related_data)
        return ordered_parts[0] if ordered_parts else None
    
    @staticmethod
    def get_next_part(course_with_related_data, current_part_id):
        """Get next part after current part"""
        ordered_parts = PartNavigationService.get_ordered_parts(course_with_related_data)
        current_index = None
        
        for idx, part in enumerate(ordered_parts):
            if part.id == current_part_id:
                current_index = idx
                break
        
        if current_index is not None and current_index < len(ordered_parts) - 1:
            return ordered_parts[current_index + 1]
        
        return None
    
    @staticmethod
    def determine_starting_part(found, introduction_id, first_part, user_progress=None, scores=None):
        """
        Determine starting part following documentation logic
        Step 2: Determine Starting Part
        
        For fresh users (no progress), always start with first part (Introduction).
        For users with progress, find first incomplete part (excluding Introduction).
        IMPORTANT: Always check if Introduction content is completed first!
        """
        # Always check if the first part (Introduction) content is completed
        # If Introduction is not completed, always show it first
        if first_part and first_part.id in introduction_id:
            # Check if Introduction content is completed
            if user_progress and first_part.id in user_progress:
                # Introduction content is completed, can proceed to next parts
                # Don't return here - continue to find next incomplete part
                pass
            else:
                # Introduction content is NOT completed, must show it first
                return first_part.id
        
        # Check if user has any actual progress (content progress, not just quiz results)
        has_content_progress = False
        if user_progress and len(user_progress) > 0:
            has_content_progress = True
        
        # If no content progress at all, start with first part (Introduction)
        if not has_content_progress:
            return first_part.id if first_part else None
        
        # If user has content progress, find first incomplete part (excluding Introduction)
        # We need to find parts where either:
        # 1. Content is not completed, OR
        # 2. Content is completed but quiz is not completed
        if len(found) > 0:
            for key, value in found.items():
                # Skip Introduction parts
                if key in introduction_id:
                    continue
                
                # Check if part content is completed
                part_content_completed = key in user_progress if user_progress else False
                
                # Part is incomplete if:
                # - Content is not completed (show content), OR
                # - Content is completed but quiz is not completed (show quiz)
                is_incomplete = not part_content_completed or (part_content_completed and value == False)
                
                if is_incomplete:
                    # Return the first incomplete part that's not an Introduction
                    # This will be the next part to show after Introduction is completed
                    return key
        
        # Fallback: If Introduction is completed and no incomplete parts found, 
        # we should still not return Introduction - find the next part after Introduction
        if first_part and first_part.id in introduction_id:
            if user_progress and first_part.id in user_progress:
                # Introduction is completed - return None to let caller get next part
                return None
        
        # Fallback to first part
        return first_part.id if first_part else None


class QuizStatusService:
    """Service for quiz status and button display logic"""
    
    @staticmethod
    def calculate_quiz_pass_status(answers_data):
        """Calculate pass status for all parts with quiz results"""
        quiz_pass_status = {}
        for part_id, answer_data in answers_data.items():
            correct_count = answer_data.get('correct', 0)
            incorrect_count = answer_data.get('incorrect', 0)
            total_questions = correct_count + incorrect_count
            if total_questions > 0:
                score_percent = int((correct_count / total_questions) * 100)
                quiz_pass_status[part_id] = score_percent >= 60
        return quiz_pass_status
    
    @staticmethod
    def calculate_has_passed_status(user, course, answers_data):
        """Check if user has passed quiz (attempt track deleted = passed)"""
        attempt_track_part_ids = set(
            UserQuizAttemptTrack.objects.filter(user=user, course=course)
            .values_list('part_id', flat=True)
        )
        
        has_passed_quiz_status = {}
        for part_id in answers_data.keys():
            has_passed_quiz_status[part_id] = part_id not in attempt_track_part_ids
        
        return has_passed_quiz_status
    
    @staticmethod
    def determine_button_display(quiz_completed, show_quiz_id, show_part_id, has_passed_quiz_status):
        """Determine which buttons to show for current quiz"""
        show_next_button = False
        show_reattempt_button = False
        
        try:
            current_quiz_part_id = int(show_quiz_id) if show_quiz_id and show_quiz_id != -1 else None
            current_part_id_int = int(show_part_id) if show_part_id and show_part_id != '' else None
        except (ValueError, TypeError):
            return False, False
        
        if quiz_completed and current_quiz_part_id and current_quiz_part_id == current_part_id_int:
            has_passed = has_passed_quiz_status.get(current_quiz_part_id, False)
            if has_passed:
                show_next_button = True
                show_reattempt_button = False
            else:
                show_next_button = False
                show_reattempt_button = True
        
        return show_next_button, show_reattempt_button


# ============================================================================
# VIEW CLASSES - Clean Request/Response Handling
# ============================================================================

class CounselorEnrolledCourseViewV2(View):
    """
    Production-ready main course view following documentation specifications
    Handles both GET (display) and POST (quiz submission) requests
    """
    template_name = 'counselor-enrolled-course.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Check authentication before processing"""
        if not request.session.get('id'):
            return redirect('counselor:login_view')
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, *args, **kwargs):
        """Handle GET request - Display course content"""
        course_name = kwargs.get('course_name')
        if not course_name:
            return redirect('counselor:icef_view')
        
        try:
            # Log URL and reason for loading
            print("\n" + "="*80)
            print("URL LOADING - Course Page Access")
            print("="*80)
            print(f"URL: {request.build_absolute_uri()}")
            print(f"Path: {request.path}")
            print(f"Method: {request.method}")
            print(f"Reason: Initial course page load or course overview access")
            print(f"Referer: {request.META.get('HTTP_REFERER', 'Direct access or no referer')}")
            print("-"*80)
            
            # Get user and course
            user_id = request.session.get('id')
            user = CounselorUser.objects.only('id', 'username', 'email').get(id=user_id)
            course = CounselorCourse.objects.only('id', 'title').get(title=course_name)
            
            # Get course data
            course_with_related_data = CourseDataService.get_course_with_related_data(course_name)
            if not course_with_related_data:
                messages.error(request, "Course not found")
                return redirect('counselor:icef_view')
            
            # Get user progress
            progress_data = UserProgressService.get_user_progress(
                user_id, course_with_related_data, course_name
            )
            
            # Calculate completion percentage
            total_parts = progress_data['total_parts'] - len(progress_data['introduction_id'])
            completed_parts = list(set(progress_data['part_ids']) & set(progress_data['user_progress']))
            number_of_completed_parts = len(
                list(set(completed_parts) - set(progress_data['introduction_id']))
            )
            completed_percent_value = int((number_of_completed_parts / total_parts) * 100) if total_parts > 0 else 0
            
            # Log course status to server console
            print("COURSE STATUS - User Reached Course Page")
            print("="*80)
            print(f"User: {user.username} (ID: {user.id}, Email: {user.email})")
            print(f"Course: {course_name}")
            print(f"Total Parts: {progress_data['total_parts']} (excluding {len(progress_data['introduction_id'])} Introduction parts)")
            print(f"Completed Parts: {number_of_completed_parts}/{total_parts} ({completed_percent_value}%)")
            print(f"Introduction Parts: {len(progress_data['introduction_id'])} parts (IDs: {progress_data['introduction_id']})")
            print(f"Parts with Quizzes: {len(progress_data['parts_with_quizzes'])} parts")
            print(f"Quiz Results Found: {sum(1 for v in progress_data['found'].values() if v)} quizzes completed")
            print(f"Complete Status: {len(progress_data['complete_status'])} parts fully completed")
            print("-"*80)
            
            # Determine starting part (Step 2 from documentation)
            first_part = PartNavigationService.get_first_part(course_with_related_data)
            print(f"First Part: ID={first_part.id if first_part else None}, Title='{first_part.title if first_part else None}'")
            print(f"User Progress: {len(progress_data.get('user_progress', []))} parts")
            print(f"Quiz Scores: {len(progress_data.get('scores', []))} scores")
            print(f"Found (quiz results): {len([v for v in progress_data['found'].values() if v])} completed quizzes")
            
            show_part_id = PartNavigationService.determine_starting_part(
                progress_data['found'],
                progress_data['introduction_id'],
                first_part,
                progress_data.get('user_progress', []),
                progress_data.get('scores', [])
            )
            
            # If determine_starting_part returned None (Introduction completed, no incomplete parts found),
            # find the next part after Introduction
            if show_part_id is None and first_part and first_part.id in progress_data['introduction_id']:
                if first_part.id in progress_data.get('user_progress', []):
                    # Introduction is completed - get next part
                    next_part = PartNavigationService.get_next_part(course_with_related_data, first_part.id)
                    if next_part:
                        show_part_id = next_part.id
                    else:
                        # No next part - course might be completed, but still show Introduction
                        show_part_id = first_part.id
            
            print(f"Determined Starting Part ID: {show_part_id}")
            print(f"Is Starting Part an Introduction? {show_part_id in progress_data['introduction_id'] if show_part_id else 'N/A'}")
            
            # Initialize quiz display
            show_quiz_id = -1
            quiz_completed = False
            
            # Check if part is completed and quiz status
            # Introduction parts never have quizzes - skip all quiz logic for them
            if (show_part_id and 
                show_part_id in progress_data['complete_status'] and
                show_part_id not in progress_data['introduction_id']):
                # Only check quiz completion for non-Introduction parts
                if show_part_id in progress_data['found'] and progress_data['found'][show_part_id]:
                    # Check if part actually has quizzes before showing quiz
                    part = Part.objects.prefetch_related('quizzes').filter(id=show_part_id).first()
                    if part and part.quizzes.exists():
                        quiz_completed = True
                        show_quiz_id = show_part_id
                    else:
                        # Part has no quiz - keep show_quiz_id as -1 to show part content
                        show_quiz_id = -1
            
            # Update resume tracking
            if show_part_id:
                try:
                    part_obj = Part.objects.select_related('chapter').get(id=show_part_id)
                    UserProgressTrack.objects.update_or_create(
                        user=user,
                        course=course,
                        defaults={'resume_part': part_obj}
                    )
                    resume_chapter_id = part_obj.chapter.id
                except Part.DoesNotExist:
                    resume_chapter_id = course_with_related_data.chapters.all()[0].id
            else:
                resume_chapter_id = course_with_related_data.chapters.all()[0].id
            
            # Get re-attempt status
            resume_id, time_difference, no_of_attempt, window_closed_time = (
                QuizAttemptService.get_reattempt_status(
                    user, course, show_part_id,
                    progress_data['found'],
                    progress_data['introduction_id'],
                    progress_data.get('user_progress', []),
                    progress_data.get('scores', [])
                )
            )
            
            # Override with resume_id if different
            # CRITICAL: Never override if show_part_id is an Introduction part that's not completed
            # This ensures Introduction parts are always shown first when not completed
            if resume_id != show_part_id and resume_id != -1:
                # Check if show_part_id is an Introduction part that's not completed
                show_part_is_intro = show_part_id in progress_data['introduction_id'] if show_part_id else False
                show_part_completed = show_part_id in progress_data['user_progress'] if show_part_id else False
                
                # Don't override if show_part_id is an incomplete Introduction part
                if show_part_is_intro and not show_part_completed:
                    # Keep show_part_id as the Introduction part
                    pass
                # Check if the resume_id part is an Introduction part
                elif resume_id not in progress_data['introduction_id']:
                    show_part_id = resume_id
                    # Check if part has quizzes before setting show_quiz_id
                    part = Part.objects.prefetch_related('quizzes').filter(id=resume_id).first()
                    if part and part.quizzes.exists() and resume_id in progress_data['found'] and progress_data['found'][resume_id]:
                        show_quiz_id = resume_id
                        quiz_completed = True
                    else:
                        # Part has no quiz or quiz not completed - show part content
                        show_quiz_id = -1
                else:
                    # For Introduction parts, keep show_quiz_id as -1
                    show_part_id = resume_id
                    show_quiz_id = -1
            
            # Get part and quiz content
            part_content_testing = None
            quiz_content_testing = None
            if show_part_id:
                try:
                    part_content_testing = Part.objects.only(
                        'id', 'title', 'description', 'index'
                    ).get(id=show_part_id)
                    print(f"✓ Part content fetched successfully: ID={part_content_testing.id}, Title='{part_content_testing.title}', Index={part_content_testing.index}")
                    quiz_content_testing = Part.objects.prefetch_related(
                        'quizzes__questions__answers'
                    ).only('id').filter(id=show_part_id).first()
                except Part.DoesNotExist as e:
                    print(f"✗ ERROR: Part not found for show_part_id={show_part_id}: {str(e)}")
                except Exception as e:
                    print(f"✗ ERROR: Failed to fetch part content for show_part_id={show_part_id}: {str(e)}")
            else:
                print("✗ ERROR: show_part_id is None/0, cannot fetch part content!")
            
            # Get next part
            next_part = PartNavigationService.get_next_part(
                course_with_related_data, show_part_id
            )
            next_part_for_quiz = next_part if quiz_completed else None
            
            # Calculate quiz status (exclude Introduction parts - they have no quizzes)
            quiz_answers_data = {
                part_id: data 
                for part_id, data in progress_data['answers_data'].items()
                if part_id not in progress_data['introduction_id']
            }
            quiz_pass_status = QuizStatusService.calculate_quiz_pass_status(
                quiz_answers_data
            )
            has_passed_quiz_status = QuizStatusService.calculate_has_passed_status(
                user, course, quiz_answers_data
            )
            show_next_button, show_reattempt_button = QuizStatusService.determine_button_display(
                quiz_completed, show_quiz_id, show_part_id, has_passed_quiz_status
            )
            
            # Check certificate
            certificate_grant, grade, issued_date, certificate_code = (
                CertificateService.check_and_generate_certificate(
                    user, course, progress_data
                )
            )
            
            # Get course title
            course_title = ''
            if course_name == 'UK':
                course_title = 'UK Agent and Counsellor Training Course'
            elif course_name == 'Germany':
                course_title = 'Germany Agent and Counsellor Training Course'
            
            # Check autocomplete
            autocomplete_enabled = request.session.get(f'autocomplete_{course_name}', False)
            
            # Build context
            context = {
                'course': course_with_related_data,
                'scores': progress_data['scores'],
                'found': progress_data['found'],
                'answers_data': progress_data['answers_data'],
                'part_scores': progress_data['part_scores'],
                'correct_answers': progress_data['correct_answers'],
                'incorrect_answers': progress_data['incorrect_answers'],
                'complete_status': progress_data['complete_status'],
                'course_title': course_title,
                'certificate_grant': certificate_grant,
                'issued_date': issued_date,
                'certificate_code': certificate_code,
                'grade': grade,
                'user': user,  # Pass full user object for avatar display
                'user_name': user.username,
                'show_part_id': show_part_id,
                'show_quiz_id': show_quiz_id,  # Keep -1 for template logic (template checks show_quiz_id == -1)
                'resume_chapter_id': resume_chapter_id,
                'total_parts': total_parts,
                'number_of_completed_parts': number_of_completed_parts,
                'completed_percent_value': completed_percent_value,
                'part_content_testing': part_content_testing,
                'quiz_content_testing': quiz_content_testing,
                'no_of_attempt': no_of_attempt,
                'time_difference': time_difference,
                'window_closed_time': window_closed_time,
                'introduction_id': progress_data['introduction_id'],
                'autocomplete_enabled': autocomplete_enabled,
                'course_name': course_name,
                'next_part': next_part,
                'quiz_completed': quiz_completed,
                'next_part_for_quiz': next_part_for_quiz,
                'quiz_pass_status': quiz_pass_status,
                'has_passed_quiz_status': has_passed_quiz_status,
                'show_next_button': show_next_button,
                'show_reattempt_button': show_reattempt_button,
                'debug': settings.DEBUG,
            }
            
            return render(request, self.template_name, context)
            
        except CounselorUser.DoesNotExist:
            messages.error(request, "User not found")
            return redirect('counselor:login_view')
        except CounselorCourse.DoesNotExist:
            messages.error(request, "Course not found")
            return redirect('counselor:icef_view')
        except Exception as e:
            logger.error(f"Error in CounselorEnrolledCourseViewV2.get: {str(e)}")
            messages.error(request, "An error occurred. Please try again.")
            return redirect('counselor:icef_view')
    
    def post(self, request, *args, **kwargs):
        """Handle POST request - Process quiz submission"""
        try:
            # Log URL and reason for loading
            print("\n" + "="*80)
            print("URL LOADING - Quiz Submission")
            print("="*80)
            print(f"URL: {request.build_absolute_uri()}")
            print(f"Path: {request.path}")
            print(f"Method: {request.method}")
            print(f"Reason: Quiz submission/answer processing")
            print(f"Referer: {request.META.get('HTTP_REFERER', 'Direct access or no referer')}")
            print("-"*80)
            
            # Parse request data
            part_id_list = request.POST.getlist('part_id')
            if not part_id_list:
                return JsonResponse({'success': False, 'message': 'Part ID is required'}, status=400)
            
            part_id = int(part_id_list[0])
            course_name = request.POST.get('course_name', '')
            if not course_name:
                return JsonResponse({'success': False, 'message': 'Course name is required'}, status=400)
            
            # Parse found and introduction_id
            found = {}
            found_str = request.POST.get('found', '{}')
            if found_str and found_str.strip():
                try:
                    found = ast.literal_eval(found_str)
                    if not isinstance(found, dict):
                        found = {}
                except (ValueError, SyntaxError):
                    try:
                        found = json.loads(found_str)
                        if not isinstance(found, dict):
                            found = {}
                    except (ValueError, json.JSONDecodeError):
                        found = {}
            
            introduction_id = []
            introduction_id_list = request.POST.getlist('introduction_id')
            if introduction_id_list and introduction_id_list[0]:
                try:
                    introduction_id = ast.literal_eval(introduction_id_list[0])
                    if not isinstance(introduction_id, list):
                        introduction_id = []
                except (ValueError, SyntaxError, IndexError):
                    try:
                        introduction_id = json.loads(introduction_id_list[0])
                        if not isinstance(introduction_id, list):
                            introduction_id = []
                    except (ValueError, json.JSONDecodeError, IndexError):
                        introduction_id = []
            
            # Get user and course
            user_id = request.session.get('id')
            user = get_object_or_404(CounselorUser, id=user_id)
            course = get_object_or_404(CounselorCourse, title=course_name)
            part = get_object_or_404(Part, id=part_id)
            
            # Validate: Introduction parts cannot have quizzes
            if part.title == 'Introduction':
                return JsonResponse({
                    'success': False, 
                    'message': 'Introduction parts do not have quizzes'
                }, status=400)
            
            # Process quiz answers
            results = {}
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
                    
                    correct_answers_map[f'ques_{question.id}'] = {
                        'correct_ans': correct_answer.answer_text if correct_answer else None,
                        'selected_ans': user_answer.answer_text if user_answer else None,
                    }
                
                results[part.id]['quiz_results'].append({
                    'quiz_id': quiz.id,
                    'total_questions_in_quiz': total_questions_each_quiz,
                    'correct_option': correct_answers_map,
                    'quiz_result': {
                        'correct_answers': results[part.id]['correct_count'],
                        'incorrect_answers': results[part.id]['incorrect_count'],
                    }
                })
            
            # Save quiz results
            data = {
                "userId": user_id,
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
            
            quiz_results, created = QuizResults.objects.update_or_create(
                user=user, course=course
            )
            
            if isinstance(quiz_results.scores, str) or not isinstance(quiz_results.scores, list):
                quiz_results.scores = []
            
            for new_score in data["scores"]:
                part_id = new_score["part_id"]
                quiz_id = new_score["quiz_id"]
                existing_score = next(
                    (score for score in quiz_results.scores 
                     if score.get("part_id") == part_id and score.get("quiz_id") == quiz_id),
                    None
                )
                if existing_score:
                    existing_score.update(new_score)
                else:
                    quiz_results.scores.append(new_score)
            
            quiz_results.save()
            
            # Calculate pass/fail
            quiz = results[part.id]['quiz_results'][0] if results[part.id]['quiz_results'] else {}
            score_percent = 0
            if quiz:
                score_percent = int((
                    quiz['quiz_result']['correct_answers'] / 
                    quiz["total_questions_in_quiz"]
                ) * 100)
            
            score_pass = 1 if score_percent >= 60 else 0
            
            # Handle attempt tracking (following documentation)
            if score_pass == 1:
                # Passed: delete attempt track
                UserQuizAttemptTrack.objects.filter(
                    user=user, course=course, part=part
                ).delete()
            else:
                # Failed: update or create attempt track
                try:
                    attempt = UserQuizAttemptTrack.objects.get(
                        user=user, course=course, part=part
                    )
                    if attempt.no_of_attempt == 1:
                        attempt.no_of_attempt = 2
                        attempt.window_closed_time = timezone.now()
                    elif attempt.no_of_attempt == 2:
                        attempt.no_of_attempt = 3
                    attempt.save()
                except UserQuizAttemptTrack.DoesNotExist:
                    UserQuizAttemptTrack.objects.create(
                        user=user, course=course, part=part, no_of_attempt=1
                    )
            
            # Get re-attempt status
            show_part_id = int(request.POST.get('show_part_id', 0))
            resume_id, time_difference, no_of_attempt, window_closed_time = (
                QuizAttemptService.get_reattempt_status(
                    user, course, show_part_id, found, introduction_id
                )
            )
            
            response_data = {
                'scores': data['scores'],
                'no_of_attempt': no_of_attempt,
                'time_difference': time_difference.total_seconds() if time_difference else None,
                'window_closed_time': window_closed_time.isoformat() if window_closed_time else None,
                'success': True
            }
            
            return JsonResponse(response_data)
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing request data: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Invalid request data'}, status=400)
        except Exception as e:
            logger.error(f"Error in CounselorEnrolledCourseViewV2.post: {str(e)}")
            return JsonResponse({'success': False, 'message': 'Internal server error'}, status=500)


class FetchCurrentPartViewV2(View):
    """
    Production-ready view for fetching specific part content
    Following Step 3 from documentation
    """
    template_name = 'counselor-enrolled-course.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Check authentication before processing"""
        if not request.session.get('id'):
            return redirect('counselor:login_view')
        return super().dispatch(request, *args, **kwargs)
    
    def get(self, request, *args, **kwargs):
        """Handle GET request - Display specific part/quiz"""
        course_name = kwargs.get('course_name')
        current_part_id = kwargs.get('current_part_id')
        part_or_quiz = kwargs.get('part_or_quiz', 1)  # 1 = part, 0 = quiz
        
        try:
            # Log URL and reason for loading
            print("\n" + "="*80)
            print("URL LOADING - Part/Quiz Navigation")
            print("="*80)
            print(f"URL: {request.build_absolute_uri()}")
            print(f"Path: {request.path}")
            print(f"Method: {request.method}")
            print(f"Reason: Navigating to {'Quiz' if part_or_quiz == 0 else 'Part Content'} (Part ID: {current_part_id})")
            print(f"Referer: {request.META.get('HTTP_REFERER', 'Direct access or no referer')}")
            print("-"*80)
            
            # Get user and course
            user_id = request.session.get('id')
            user = CounselorUser.objects.only('id', 'username', 'email').get(id=user_id)
            course = CounselorCourse.objects.only('id', 'title').get(title=course_name)
            
            # Get course data
            course_with_related_data = CourseDataService.get_course_with_related_data(course_name)
            if not course_with_related_data:
                messages.error(request, "Course not found")
                return redirect('counselor:icef_view')
            
            # Get user progress
            progress_data = UserProgressService.get_user_progress(
                user_id, course_with_related_data, course_name
            )
            
            # Calculate completion
            total_parts = progress_data['total_parts'] - len(progress_data['introduction_id'])
            completed_parts = list(set(progress_data['part_ids']) & set(progress_data['user_progress']))
            number_of_completed_parts = len(
                list(set(completed_parts) - set(progress_data['introduction_id']))
            )
            completed_percent_value = int((number_of_completed_parts / total_parts) * 100) if total_parts > 0 else 0
            
            # Log course status to server console
            print("COURSE STATUS - User Navigated to Part")
            print("="*80)
            print(f"User: {user.username} (ID: {user.id}, Email: {user.email})")
            print(f"Course: {course_name}")
            print(f"Navigating to Part ID: {current_part_id}, part_or_quiz: {part_or_quiz} ({'Quiz' if part_or_quiz == 0 else 'Content'})")
            print(f"Total Parts: {progress_data['total_parts']} (excluding {len(progress_data['introduction_id'])} Introduction parts)")
            print(f"Completed Parts: {number_of_completed_parts}/{total_parts} ({completed_percent_value}%)")
            print("-"*80)
            
            # Check if user is trying to access a completed Introduction part
            # If so, redirect to the next part instead
            is_introduction = current_part_id in progress_data['introduction_id']
            if is_introduction:
                introduction_completed = current_part_id in progress_data.get('user_progress', [])
                if introduction_completed:
                    # Introduction is completed - get next part and redirect
                    next_part = PartNavigationService.get_next_part(
                        course_with_related_data, current_part_id
                    )
                    if next_part:
                        # Redirect to next part
                        return redirect('counselor:fetch_current_part', 
                                      course_name=course_name,
                                      current_part_id=next_part.id,
                                      part_or_quiz=1)
                    else:
                        # No next part - redirect to course overview
                        return redirect('counselor:counselor_enrolled_course_param', course_name=course_name)
            
            # Determine what to show
            show_part_id = current_part_id
            show_quiz_id = -1
            quiz_completed = False
            
            # Handle part_or_quiz parameter (Step 5 from documentation)
            # Introduction parts never have quizzes, so skip quiz logic for them
            
            # Check if quiz is completed (only for non-Introduction parts)
            if not is_introduction and current_part_id in progress_data['found'] and progress_data['found'][current_part_id]:
                quiz_completed = True
            
            if part_or_quiz == 0:  # Accessing quiz
                if not is_introduction and current_part_id in progress_data['complete_status']:
                    # Check if part actually has quizzes before showing quiz
                    part = Part.objects.prefetch_related('quizzes').filter(id=current_part_id).first()
                    if part and part.quizzes.exists():
                        # Part completed and has quiz - quiz accessible
                        show_quiz_id = current_part_id
                    else:
                        # Part has no quiz - show part content instead
                        show_quiz_id = -1
                        show_part_id = current_part_id
                else:
                    # Quiz locked or Introduction part, show part content
                    show_quiz_id = -1
                    show_part_id = current_part_id
            else:  # Viewing part content (part_or_quiz=1)
                # When viewing part content, always show part content first
                # Only show quiz if explicitly requested (part_or_quiz=0)
                # For Introduction parts, always keep show_quiz_id as -1
                if not is_introduction:
                    # Check if part has quiz and is completed
                    part = Part.objects.prefetch_related('quizzes').filter(id=current_part_id).first()
                    # Only auto-show quiz if part is completed AND has quiz AND quiz is already completed
                    # Otherwise, show part content (show_quiz_id stays -1)
                    if part and part.quizzes.exists() and current_part_id in progress_data['complete_status'] and quiz_completed:
                        # Part completed, has quiz, and quiz is completed - show quiz results
                        show_quiz_id = current_part_id
                    else:
                        # Show part content (not quiz)
                        show_quiz_id = -1
                # For Introduction parts, always keep show_quiz_id as -1
            
            # Get part and quiz content
            part_content_testing = None
            quiz_content_testing = None
            
            if show_part_id:
                try:
                    # Fetch part with chapter relationship and required fields for template
                    # Use select_related to get chapter, but don't use .only() to ensure all fields are available
                    part_content_testing = Part.objects.select_related('chapter').get(id=show_part_id)
                    resume_chapter_id = part_content_testing.chapter.id
                except Part.DoesNotExist:
                    resume_chapter_id = course_with_related_data.chapters.all()[0].id
                    part_content_testing = None
                
                quiz_content_testing = Part.objects.prefetch_related(
                    'quizzes__questions__answers'
                ).only('id').filter(id=show_part_id).first()
            else:
                resume_chapter_id = course_with_related_data.chapters.all()[0].id
            
            # Get re-attempt status
            resume_id, time_difference, no_of_attempt, window_closed_time = (
                QuizAttemptService.get_reattempt_status(
                    user, course, current_part_id,
                    progress_data['found'],
                    progress_data['introduction_id'],
                    progress_data.get('user_progress', []),
                    progress_data.get('scores', [])
                )
            )
            
            # Get next part
            next_part = PartNavigationService.get_next_part(
                course_with_related_data, show_part_id
            )
            next_part_for_quiz = next_part if quiz_completed else None
            
            # Log current part and next part information
            print(f"Final show_part_id: {show_part_id}")
            print(f"Final show_quiz_id: {show_quiz_id}")
            
            if show_part_id:
                try:
                    current_part = Part.objects.only('id', 'title').get(id=show_part_id)
                    is_intro = show_part_id in progress_data['introduction_id']
                    print(f"Current Part: ID={show_part_id}, Title='{current_part.title}' ({'Introduction' if is_intro else 'Regular'})")
                    
                    # Check if part_content_testing will be available
                    try:
                        part_test = Part.objects.only('id', 'title', 'description', 'index').get(id=show_part_id)
                        print(f"Part Content Available: Yes (Title: '{part_test.title}', Index: {part_test.index}, Description: {bool(part_test.description)})")
                    except Exception as e:
                        print(f"Part Content Available: No - {str(e)}")
                except Exception as e:
                    print(f"Current Part: ID={show_part_id} (details not available - {str(e)})")
            else:
                print("ERROR: show_part_id is None or 0 - No part will be displayed!")
            
            if next_part:
                print(f"Next Part: ID={next_part.id}, Title='{next_part.title}'")
            else:
                print("Next Part: None (course completed or last part)")
            
            # Log quiz status if applicable
            if show_quiz_id != -1:
                print(f"Quiz Status: Showing quiz for part ID={show_quiz_id}, Completed={quiz_completed}")
            else:
                print(f"Quiz Status: No quiz (show_quiz_id={show_quiz_id})")
            
            print("="*80 + "\n")
            
            # Calculate quiz status (exclude Introduction parts - they have no quizzes)
            quiz_answers_data = {
                part_id: data 
                for part_id, data in progress_data['answers_data'].items()
                if part_id not in progress_data['introduction_id']
            }
            quiz_pass_status = QuizStatusService.calculate_quiz_pass_status(
                quiz_answers_data
            )
            has_passed_quiz_status = QuizStatusService.calculate_has_passed_status(
                user, course, quiz_answers_data
            )
            show_next_button, show_reattempt_button = QuizStatusService.determine_button_display(
                quiz_completed, show_quiz_id, show_part_id, has_passed_quiz_status
            )
            
            # Check certificate
            certificate_grant, grade, issued_date, certificate_code = (
                CertificateService.check_and_generate_certificate(
                    user, course, progress_data
                )
            )
            
            # Get course title
            course_title = ''
            if course_name == 'UK':
                course_title = 'UK Agent and Counsellor Training Course'
            elif course_name == 'Germany':
                course_title = 'Germany Agent and Counsellor Training Course'
            
            # Check autocomplete
            autocomplete_enabled = request.session.get(f'autocomplete_{course_name}', False)
            
            # Build context
            context = {
                'course': course_with_related_data,
                'scores': progress_data['scores'],
                'found': progress_data['found'],
                'answers_data': progress_data['answers_data'],
                'part_scores': progress_data['part_scores'],
                'correct_answers': progress_data['correct_answers'],
                'incorrect_answers': progress_data['incorrect_answers'],
                'complete_status': progress_data['complete_status'],
                'course_title': course_title,
                'certificate_grant': certificate_grant,
                'issued_date': issued_date,
                'certificate_code': certificate_code,
                'grade': grade,
                'user': user,  # Pass full user object for avatar display
                'user_name': user.username,
                'show_part_id': show_part_id,
                'show_quiz_id': show_quiz_id,  # Keep -1 for template logic (template checks show_quiz_id == -1)
                'resume_chapter_id': resume_chapter_id,
                'total_parts': total_parts,
                'number_of_completed_parts': number_of_completed_parts,
                'completed_percent_value': completed_percent_value,
                'part_content_testing': part_content_testing,
                'quiz_content_testing': quiz_content_testing,
                'no_of_attempt': no_of_attempt,
                'time_difference': time_difference,
                'window_closed_time': window_closed_time,
                'introduction_id': progress_data['introduction_id'],
                'autocomplete_enabled': autocomplete_enabled,
                'course_name': course_name,
                'next_part': next_part,
                'quiz_completed': quiz_completed,
                'next_part_for_quiz': next_part_for_quiz,
                'quiz_pass_status': quiz_pass_status,
                'has_passed_quiz_status': has_passed_quiz_status,
                'show_next_button': show_next_button,
                'show_reattempt_button': show_reattempt_button,
                'debug': settings.DEBUG,
            }
            
            return render(request, self.template_name, context)
            
        except Exception as e:
            logger.error(f"Error in FetchCurrentPartViewV2.get: {str(e)}")
            messages.error(request, "An error occurred. Please try again.")
            return redirect('counselor:counselor_enrolled_course_param', course_name=course_name)


# Keep existing utility functions for backward compatibility
@csrf_exempt
def update_part_status(request, part_id):
    """Update part completion status"""
    # Log URL and reason for loading
    print("\n" + "="*80)
    print("URL LOADING - Part Status Update")
    print("="*80)
    print(f"URL: {request.build_absolute_uri()}")
    print(f"Path: {request.path}")
    print(f"Method: {request.method}")
    print(f"Reason: Marking part as complete (Part ID: {part_id})")
    print(f"Referer: {request.META.get('HTTP_REFERER', 'Direct access or no referer')}")
    print("-"*80)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    
    if not request.session.get('id'):
        return JsonResponse({'success': False, 'message': 'Unauthorized'}, status=403)
    
    try:
        user_id = request.session.get('id')
        Counselor_user = CounselorUser.objects.get(id=user_id)
        part = Part.objects.get(id=part_id)
        
        print(f"User: {Counselor_user.username} (ID: {Counselor_user.id})")
        print(f"Part: ID={part.id}, Title='{part.title}'")
        print(f"Is Introduction? {part.title == 'Introduction'}")
        
        # Update or create the progress entry
        progress, created = CourseContentProgress.objects.update_or_create(
            user=Counselor_user, 
            part_id=part, 
            defaults={'completed': True}
        )
        
        print(f"Progress Entry: {'Created' if created else 'Updated'}, completed={progress.completed}")
        
        # Verify it was saved
        saved = CourseContentProgress.objects.filter(user=Counselor_user, part_id=part).first()
        if saved and saved.completed:
            print(f"✓ Verified: Part {part_id} marked as complete successfully")
        else:
            print(f"✗ ERROR: Part {part_id} completion status not saved correctly!")
        
        return JsonResponse({'success': True, 'message': 'Part marked as complete'})
    except CounselorUser.DoesNotExist:
        print(f"✗ ERROR: User not found (ID: {user_id})")
        return JsonResponse({'success': False, 'message': 'User not found'}, status=404)
    except Part.DoesNotExist:
        print(f"✗ ERROR: Part not found (ID: {part_id})")
        return JsonResponse({'success': False, 'message': 'Part not found'}, status=404)
    except Exception as e:
        print(f"✗ ERROR: Exception occurred: {str(e)}")
        logger.error(f"Error updating part status: {str(e)}")
        return JsonResponse({'success': False, 'message': 'Internal server error'}, status=500)
