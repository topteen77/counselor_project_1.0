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
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True, default=0,
        help_text='Course price in INR. 0 or null = free.'
    )
    created_at = models.DateTimeField(auto_now_add=True)  # Course creation date
    updated_at = models.DateTimeField(auto_now=True)  # Course last update time

    class Meta:
        verbose_name_plural = "CounselorCourses"

    def __str__(self):
        return self.title

    @property
    def is_free(self):
        return self.price is None or self.price == 0

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


class DiscountCoupon(models.Model):
    """Admin-created coupon for course payment discount. Code is case-insensitive for lookup. Can apply to multiple courses or all (empty)."""
    DISCOUNT_TYPES = (('percent', 'Percentage'), ('fixed', 'Fixed amount'))

    code = models.CharField(max_length=64, unique=True, db_index=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_TYPES, default='percent')
    value = models.DecimalField(max_digits=10, decimal_places=2, help_text='Percentage (e.g. 10) or fixed amount in INR')
    courses = models.ManyToManyField(
        CounselorCourse, blank=True, related_name='coupons',
        help_text='Leave empty for all courses; otherwise this coupon applies only to selected courses.'
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True, help_text='Leave blank for unlimited')
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Discount coupons'
        ordering = ('-created',)

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} ({self.get_discount_type_display()} {self.value})'


class CourseTrialStart(models.Model):
    """Tracks when a user started their freemium trial for a course. One per user per course."""
    user = models.ForeignKey(CounselorUser, on_delete=models.CASCADE, related_name='course_trials')
    course = models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, related_name='trial_starts')
    started_at = models.DateTimeField()
    # Set when user clicks "Back to course list" in trial-expired modal (only if they have not bought)
    expired_acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Course trial starts'
        unique_together = ('user', 'course')

    def __str__(self):
        return f'{self.user} – {self.course} from {self.started_at}'


class CoursePayment(models.Model):
    """Tracks payment attempts per user per course. is_success=True means enrolled."""
    user = models.ForeignKey(CounselorUser, on_delete=models.CASCADE, related_name='course_payments')
    course = models.ForeignKey(CounselorCourse, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon = models.ForeignKey(
        DiscountCoupon, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments'
    )
    currency = models.CharField(max_length=10, default='INR', blank=True)
    gateway_receipt = models.CharField(max_length=120, blank=True, null=True)
    gateway_order_id = models.CharField(max_length=120, blank=True, null=True)
    gateway_payment_id = models.CharField(max_length=120, blank=True, null=True)
    gateway_signature = models.CharField(max_length=120, blank=True, null=True)
    is_success = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Course payments'
        ordering = ('-created',)

    def __str__(self):
        return f'{self.user} - {self.course} - {self.amount} - {"OK" if self.is_success else "pending"}'

    def get_gateway_amount(self):
        """Amount in paise for Razorpay."""
        return int(self.amount * 100)


def payment_receipt_upload_to(instance, filename):
    return 'receipts/{0}/{1}'.format(instance.payment.id, filename)


class PaymentReceipt(models.Model):
    """One receipt per successful CoursePayment; used for download payment."""
    payment = models.OneToOneField(
        CoursePayment, on_delete=models.CASCADE, related_name='receipt'
    )
    transaction_id = models.CharField(max_length=120, blank=True)
    invoice_number = models.CharField(max_length=64, blank=True)
    invoice_pdf = models.FileField(upload_to=payment_receipt_upload_to, blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Payment receipts'

    def __str__(self):
        return f'Receipt {self.invoice_number or self.id} for payment {self.payment.id}'


class SiteLabel(models.Model):
    """Admin-configurable button and label text used across the site (listing, detail, trial modal)."""
    key = models.CharField(max_length=80, unique=True, db_index=True)
    value = models.CharField(max_length=200, help_text='Display text for this label')

    class Meta:
        verbose_name_plural = 'Site labels (buttons, ribbons)'
        ordering = ('key',)

    def __str__(self):
        return f'{self.key}: {self.value}'
