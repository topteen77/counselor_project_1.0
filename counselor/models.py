from django.db import models

# Create your models here.
from django.db import models

from django.conf import settings
from django.utils.timezone import localtime



# from core import choices
# from core.models import BaseModel, BaseMoneyModel, Configuration,SlugModel

class CounselorUser(models.Model):
    username=models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=3000)

    def __str__(self):
        return self.username
    

class CounselorCourse(models.Model):
    title = models.CharField(max_length=200, blank=True, null=True)  # Name of the course
    created_at = models.DateTimeField(auto_now_add=True)  # Course creation date
    updated_at = models.DateTimeField(auto_now=True)  # Course last update time

    class Meta:
        verbose_name_plural = "CounselorCourses"

    def __str__(self):  
        return self.title

class Chapter(models.Model):
    course = models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, related_name="chapters",blank=True, null=True)
    title = models.CharField(max_length=100)
    index =models.IntegerField(default=0)  

    class Meta:
        verbose_name_plural = "Course Chapters"

    def __str__(self):
        return self.title

class Part(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="parts",blank=True, null=True)
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    index =models.IntegerField(default=0)
    class Meta:
        verbose_name_plural = "Course Parts"

    def __str__(self):
        return self.title

class Quiz(models.Model):
    title = models.CharField(max_length=200, blank=True, null=True)
    quiz_part = models.ForeignKey(Part, related_name='quizzes', on_delete=models.CASCADE,blank=True, null=True)

    class Meta:
        verbose_name_plural = "Course Quizzes"

    def __str__(self):
        return f"Quiz: {self.title} (Part: {self.quiz_part.title})"

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, related_name='questions', on_delete=models.CASCADE,blank=True, null=True)
    question_text = models.TextField(max_length=200, blank=True, null=True)

    class Meta:
        verbose_name_plural = "Quiz Questions"

    def __str__(self):
        return f"Question: {self.question_text[:50]} (Quiz: {self.quiz.title})"

class QuizAnswers(models.Model):
    question = models.ForeignKey(Question, related_name='answers', on_delete=models.CASCADE,blank=True, null=True)
    answer_text = models.CharField(max_length=200, blank=True, null=True)
    is_correct = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "Quiz Answers"

    def __str__(self):
        return f"Answer {self.id} for Question {self.question.id}"

class QuizResults(models.Model):
    user = models.ForeignKey(CounselorUser, on_delete=models.CASCADE, blank=True, null=True
    )
    course=models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, blank=True, null=True)
    scores = models.JSONField(default=dict)
    modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        user_info = self.user.username if self.user else "Anonymous User"
        modified_time = localtime(self.modified).strftime("%Y-%m-%d %H:%M:%S")
        return f"Scores for {user_info} | Last Modified: {modified_time}"

class CourseContentProgress(models.Model):
    user = models.ForeignKey(
        CounselorUser, on_delete=models.CASCADE, blank=True, null=True
    )
    part_id = models.ForeignKey(Part,on_delete=models.CASCADE, blank=True, null=True)
    completed = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.part_id}: {self.completed}%"
    
class CounselorCertification(models.Model):
    user = models.ForeignKey(CounselorUser, on_delete=models.CASCADE, null=True, blank=True)
    course = models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, null=True, blank=True)
    certificate_code = models.CharField(max_length=8, null=True, blank=True)
    grade = models.CharField(max_length=8, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)  # Automatically set the field to now when the object is created

    class Meta:
        unique_together = ('user', 'course')  # 👈 Ensures uniqueness
        
    def _str_(self):
        return f"{self.user} - {self.certificate_code}"
    
class CourseOverviewPoints(models.Model):
    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name="points",blank=True, null=True)
    points = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Chapter Name: {self.chapter.title} \n Points: {self.points}"
    
class CourseOverviewSummary(models.Model):
    course = models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, related_name="summarys",blank=True, null=True)
    title1 = models.TextField(blank=True,null=True)  
    title2 = models.TextField(blank=True,null=True)  

    def __str__(self):
        return f"Introduction: {self.title1}\n Conclusion: {self.title2}"
    
class UserProgressTrack(models.Model):
    user = models.ForeignKey(CounselorUser, on_delete=models.CASCADE, blank=True, null=True)
    resume_part = models.ForeignKey(Part, on_delete=models.CASCADE, blank=True, null=True)
    course = models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, blank=True, null=True)

    class Meta:
        unique_together = ('user', 'course')  # 👈 Ensures uniqueness
        
    def __str__(self):
        return f"User: {self.user} , Resume_Part: {self.resume_part} , Course: {self.course}"
    

class UserQuizAttemptTrack(models.Model):
    user = models.ForeignKey('CounselorUser', on_delete=models.CASCADE, blank=True, null=True)
    course = models.ForeignKey('CounselorCourse', on_delete=models.CASCADE, blank=True, null=True)
    part = models.ForeignKey(Part,on_delete=models.CASCADE, blank=True, null=True)
    no_of_attempt = models.IntegerField(default=0)
    window_closed_time = models.DateTimeField(blank=True, null=True)  # allow null for initial save

    class Meta:
        unique_together = ('user', 'course', 'part')  # 👈 Ensures uniqueness across these fields

    def __str__(self):
        return f'{self.user} - {self.part} - Attempts: {self.no_of_attempt}'
    