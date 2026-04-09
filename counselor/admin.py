from django import forms
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.db import models
from django.db.models import Count
import nested_admin
from .models import CounselorCertification, CounselorCourse, Chapter, CounselorUser, CourseContentProgress, CourseOverviewPoints, CourseOverviewSummary, CoursePayment, DiscountCoupon, Part, PaymentReceipt, Quiz, Question, QuizAnswers, QuizResults, SiteLabel, UserProgressTrack, UserQuizAttemptTrack
from ckeditor.widgets import CKEditorWidget

class PartAdminForm(forms.ModelForm):
    description = forms.CharField(widget=CKEditorWidget(), required=False)

    class Meta:
        model = Chapter
        fields = '__all__'

def reset_user_course_data(user, course):
    """
    Utility function to reset all course-related data for a specific user and course.
    """
    # Get all parts in the course
    parts_in_course = Part.objects.filter(chapter__course=course)
    
    # Delete QuizResults for this user and course
    QuizResults.objects.filter(user=user, course=course).delete()
    
    # Delete CourseContentProgress for parts in this course
    CourseContentProgress.objects.filter(user=user, part_id__in=parts_in_course).delete()
    
    # Delete UserProgressTrack for this user and course
    UserProgressTrack.objects.filter(user=user, course=course).delete()
    
    # Delete UserQuizAttemptTrack for this user and course
    UserQuizAttemptTrack.objects.filter(user=user, course=course).delete()
    
    # Delete CounselorCertification for this user and course
    CounselorCertification.objects.filter(user=user, course=course).delete()
    
    return True

@admin.register(CounselorUser)
class CounselorUserAdmin(admin.ModelAdmin):
    list_display=('id','username','email','password')
    search_fields=('username','email','password')
    list_filter=('username',)
    actions = ['reset_course_data']
    
    def reset_course_data(self, request, queryset):
        """
        Admin action to reset course data for selected users.
        """
        if 'apply' in request.POST:
            course_ids = request.POST.getlist('courses')
            if not course_ids:
                self.message_user(request, "Please select at least one course.", level=messages.ERROR)
                return redirect(request.get_full_path())
            
            try:
                courses = CounselorCourse.objects.filter(id__in=course_ids)
                if not courses.exists():
                    self.message_user(request, "Selected course(s) do not exist.", level=messages.ERROR)
                    return redirect(request.get_full_path())
                
                # Get user IDs from POST data
                selected = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)
                users = CounselorUser.objects.filter(id__in=selected)
                
                reset_count = 0
                course_names = []
                for course in courses:
                    course_names.append(course.title)
                    for user in users:
                        reset_user_course_data(user, course)
                        reset_count += 1
                
                courses_str = ', '.join(course_names)
                self.message_user(
                    request,
                    f"Successfully reset course data for {reset_count} user-course combination(s) in course(s): {courses_str}.",
                    level=messages.SUCCESS
                )
                return redirect(request.get_full_path())
            except Exception as e:
                self.message_user(request, f"An error occurred: {str(e)}", level=messages.ERROR)
                return redirect(request.get_full_path())
        
        # Show selection form
        courses = CounselorCourse.objects.all().order_by('title')
        context = {
            'users': queryset,
            'courses': courses,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'opts': self.model._meta,
            'has_change_permission': self.has_change_permission(request),
        }
        
        from django.template.response import TemplateResponse
        return TemplateResponse(
            request,
            'admin/counselor/counseloruser/reset_course_data.html',
            context
        )
    
    reset_course_data.short_description = "Reset course data for selected users"

class QuizAnswersInline(nested_admin.NestedTabularInline):
    model = QuizAnswers
    fields = ('answer_text', 'is_correct')
    extra = 1

class QuestionInline(nested_admin.NestedStackedInline):
    model = Question
    fields = ('question_text',)
    extra = 1
    inlines = [QuizAnswersInline]

class QuizAdmin(nested_admin.NestedModelAdmin):
    list_display = ('title', 'part_link')
    search_fields = (
        'title',
        'quiz_part__title',
        'quiz_part__chapter__title',
        'quiz_part__chapter__course__title',
    )
    list_filter = (
        ('quiz_part__chapter__course', admin.RelatedOnlyFieldListFilter),
        ('quiz_part__chapter', admin.RelatedOnlyFieldListFilter),
        'quiz_part',
    )
    list_select_related = ('quiz_part', 'quiz_part__chapter', 'quiz_part__chapter__course')
    inlines = [QuestionInline]

    @admin.display(description='Part')
    def part_link(self, obj):
        part = obj.quiz_part
        if not part:
            return '—'
        base = reverse('admin:counselor_part_changelist')
        # Part admin list, scoped to this part's chapter (same screen as Parts in admin)
        params = {}
        if part.chapter_id:
            params['chapter__id__exact'] = str(part.chapter_id)
        url = f'{base}?{urlencode(params)}' if params else base
        return format_html('<a href="{}">{}</a>', url, part)

class PartAdmin(admin.ModelAdmin):
    form = PartAdminForm
    list_display = ('title', 'chapter', 'index', 'quiz_count')
    fields = ('title', 'chapter', 'description','index')
    search_fields = ('title',)
    list_filter = ('chapter',)
    ordering = ('title',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_quiz_count=Count('quizzes'))

    @admin.display(description='Quizzes')
    def quiz_count(self, obj):
        n = getattr(obj, '_quiz_count', obj.quizzes.count())
        base = reverse('admin:counselor_quiz_changelist')
        params = {'quiz_part__id__exact': str(obj.pk)}
        return format_html(
            '<a href="{}">{}</a>',
            f'{base}?{urlencode(params)}',
            n,
        )

class ChapterInline(admin.StackedInline):
    model = Chapter
    extra = 1

class PartInline(admin.StackedInline):
    form = PartAdminForm
    model = Part
    extra = 1

@admin.register(CounselorCourse)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'chapter_count', 'created_at', 'updated_at')
    search_fields = ('title',)
    inlines = [ChapterInline]
    list_filter = ('created_at',)
    ordering = ('-created_at',)
    actions = ['reset_all_users_course_data']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_chapter_count=Count('chapters'))

    @admin.display(description='Chapters')
    def chapter_count(self, obj):
        n = getattr(obj, '_chapter_count', obj.chapters.count())
        base = reverse('admin:counselor_chapter_changelist')
        params = {'course__id__exact': str(obj.pk)}
        return format_html(
            '<a href="{}">{}</a>',
            f'{base}?{urlencode(params)}',
            n,
        )
    
    def reset_all_users_course_data(self, request, queryset):
        """
        Admin action to reset course data for all users in selected courses.
        """
        reset_count = 0
        course_count = 0
        
        for course in queryset:
            # Get all users who have data for this course
            users_with_data = CounselorUser.objects.filter(
                models.Q(quizresults__course=course) |
                models.Q(coursecontentprogress__part_id__chapter__course=course) |
                models.Q(userprogresstrack__course=course) |
                models.Q(userquizattempttrack__course=course) |
                models.Q(counselorcertification__course=course)
            ).distinct()
            
            for user in users_with_data:
                reset_user_course_data(user, course)
                reset_count += 1
            
            course_count += 1
        
        self.message_user(
            request,
            f"Successfully reset course data for {reset_count} user-course combination(s) across {course_count} course(s).",
            level=messages.SUCCESS
        )
    
    reset_all_users_course_data.short_description = "Reset all users' data for selected courses"

class ChapterAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'index', 'part_count')
    search_fields = ('title', 'course__title')
    inlines = [PartInline]
    list_filter = ('course',)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_part_count=Count('parts'))

    @admin.display(description='Parts')
    def part_count(self, obj):
        n = getattr(obj, '_part_count', obj.parts.count())
        base = reverse('admin:counselor_part_changelist')
        params = {'chapter__id__exact': str(obj.pk)}
        return format_html(
            '<a href="{}">{}</a>',
            f'{base}?{urlencode(params)}',
            n,
        )


@admin.register(QuizResults)
class QuizResultsAdmin(admin.ModelAdmin):
    list_display = ('user','course', 'scores')
    list_filter = ('modified',)
    actions = ['reset_user_course_from_results']

    def pretty_scores(self, obj):
        import json
        return json.dumps(obj.scores, indent=2)
    
    pretty_scores.short_description = 'Scores (Pretty Format)'
    
    def reset_user_course_from_results(self, request, queryset):
        """
        Admin action to reset all course data for users/courses from selected quiz results.
        """
        reset_count = 0
        processed_combinations = set()
        
        for quiz_result in queryset:
            if quiz_result.user and quiz_result.course:
                combination = (quiz_result.user.id, quiz_result.course.id)
                if combination not in processed_combinations:
                    reset_user_course_data(quiz_result.user, quiz_result.course)
                    processed_combinations.add(combination)
                    reset_count += 1
        
        self.message_user(
            request,
            f"Successfully reset course data for {reset_count} user-course combination(s).",
            level=messages.SUCCESS
        )
    
    reset_user_course_from_results.short_description = "Reset all course data for selected quiz results"

@admin.register(CourseContentProgress)
class ContentProgressAdmin(admin.ModelAdmin):
    list_display = ('user','part_id', 'completed')
    list_filter = ('completed',)
    search_fields = ('part_id',)
    ordering = ('part_id',)

@admin.register(CounselorCertification)
class CounselorCertificationAdmin(admin.ModelAdmin):
    list_display=('user','course','certificate_code','grade','created_at')
    list_filter=('grade','course')
    search_fields=('user','grade')

@admin.register(CourseOverviewPoints)
class CourseOverviewPointsAdmin(admin.ModelAdmin):
    list_display=('points','chapter')
    search_fields=('points','chapter')
    list_filter=('chapter',)

@admin.register(CourseOverviewSummary)
class CourseOverviewSummaryAdmin(admin.ModelAdmin):
    list_display=('title1','title2')
    search_fields=('title1','title2')
    list_filter=('course',)

@admin.register(UserProgressTrack)
class UserProgressTrackAdmin(admin.ModelAdmin):
    list_display=('user','resume_part','course')
    search_fields=('user','resume_part','course')
    list_filter=('course',)

@admin.register(UserQuizAttemptTrack)
class UserQuizAttemptTrackAdmin(admin.ModelAdmin):
    list_display = ('user','course','part','no_of_attempt','window_closed_time')
    search_fields = ('user','course','part')
    list_filter = ('user','course','part')
    
# Registering models
# admin.site.register(CourseOverviewPoints, CourseOverviewPointsAdmin)
def _generate_random_code(prefix, length=8):
    import random
    import string
    chars = string.ascii_uppercase + string.digits
    return prefix + '_' + ''.join(random.choices(chars, k=length))


class DiscountCouponAdminForm(forms.ModelForm):
    """Optional: generate N more codes with same settings when saving."""
    generate_count = forms.IntegerField(
        min_value=0, max_value=100, required=False, initial=0,
        help_text='Generate this many additional coupon codes with same settings (codes will be PREFIX_random).'
    )

    class Meta:
        model = DiscountCoupon
        fields = '__all__'


@admin.register(DiscountCoupon)
class DiscountCouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'value', 'courses_display', 'times_used', 'max_uses', 'is_active', 'valid_from', 'valid_until', 'created')
    list_filter = ('is_active', 'discount_type')
    search_fields = ('code',)
    readonly_fields = ('times_used', 'created')
    form = DiscountCouponAdminForm
    filter_horizontal = ('courses',)

    def courses_display(self, obj):
        if obj.pk:
            names = list(obj.courses.values_list('title', flat=True))
            return ', '.join(names) if names else 'All courses'
        return '—'

    courses_display.short_description = 'Courses'

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        generate_count = form.cleaned_data.get('generate_count') or 0
        if generate_count > 0:
            prefix = (obj.code or '').strip().upper()
            created = []
            course_ids = list(obj.courses.values_list('id', flat=True))
            for _ in range(generate_count):
                new_code = _generate_random_code(prefix)
                while DiscountCoupon.objects.filter(code__iexact=new_code).exists():
                    new_code = _generate_random_code(prefix)
                dup = DiscountCoupon(
                    code=new_code.upper() if new_code else new_code,
                    discount_type=obj.discount_type,
                    value=obj.value,
                    valid_from=obj.valid_from,
                    valid_until=obj.valid_until,
                    max_uses=obj.max_uses,
                    is_active=obj.is_active,
                )
                dup.save()
                if course_ids:
                    dup.courses.set(course_ids)
                created.append(dup.code)
            messages.success(request, f'Generated {len(created)} coupon(s): {", ".join(created)}')


@admin.register(CoursePayment)
class CoursePaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'course', 'amount', 'discount_amount', 'coupon', 'is_success', 'gateway_payment_id', 'created')
    list_filter = ('is_success', 'course')
    search_fields = ('user__username', 'user__email', 'gateway_order_id', 'gateway_payment_id')
    readonly_fields = ('created', 'updated')


@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ('id', 'payment', 'transaction_id', 'invoice_number', 'created')
    search_fields = ('transaction_id', 'invoice_number')
    readonly_fields = ('created',)


@admin.register(SiteLabel)
class SiteLabelAdmin(admin.ModelAdmin):
    list_display = ('key', 'value')
    search_fields = ('key', 'value')
    list_editable = ('value',)


admin.site.register(Chapter, ChapterAdmin)
admin.site.register(Part, PartAdmin)
admin.site.register(Quiz, QuizAdmin)

