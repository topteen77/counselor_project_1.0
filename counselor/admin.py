from django import forms
from django.contrib import admin
from django.contrib import messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html, strip_tags
import html
import re
from django.utils.http import urlencode
from django.db import models
from django.db.models import Count
import nested_admin
from .models import CounselorCertification, CounselorCourse, Chapter, CounselorUser, CourseContentProgress, CourseOverviewPoints, CourseOverviewSummary, CoursePayment, DiscountCoupon, Part, PaymentReceipt, Quiz, Question, QuizAnswers, QuizResults, SiteLabel, UserProgressTrack, UserQuizAttemptTrack
from ckeditor.widgets import CKEditorWidget

def _overview_plain(value):
    text = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", " ", value or "", flags=re.I)
    text = html.unescape(strip_tags(text))
    text = " ".join(text.split())
    if len(text) > 180:
        return text[:180] + "…"
    return text or "—"

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

def _default_asset_preview(asset, missing_message):
    if not asset:
        return missing_message
    from django.templatetags.static import static
    preview = ""
    if asset["exists"]:
        preview = format_html(
            '<img src="{}" alt="" style="display:block;max-width:160px;max-height:160px;margin:0 0 8px;border-radius:8px;background:#f4f4f5;" />',
            static(asset["static_name"]),
        )
    status = ""
    if not asset["exists"]:
        status = format_html('<div>This file is not in the folder yet.</div>')
    return format_html(
        '{}<code style="display:block;white-space:normal;word-break:break-all;">{}</code>{}',
        preview,
        asset["relative"],
        status,
    )


@admin.register(CounselorCourse)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'price', 'chapter_count', 'course_preview', 'created_at', 'updated_at')
    fields = (
        'title', 'price',
        'default_logo_preview', 'logo',
        'default_overview_preview', 'overview_image',
    )
    readonly_fields = ('default_logo_preview', 'default_overview_preview')
    search_fields = ('title',)
    inlines = [ChapterInline]
    list_filter = ('created_at',)
    ordering = ('-created_at',)
    actions = ['reset_all_users_course_data', 'delete_course_and_files']
    change_list_template = "admin/counselor/counselorcourse/change_list.html"

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def get_urls(self):
        from django.urls import path
        custom = [
            path(
                "import-word/",
                self.admin_site.admin_view(self.import_word_view),
                name="counselor_counselorcourse_import_word",
            ),
            path(
                "import-word/preview/",
                self.admin_site.admin_view(self.import_word_preview_view),
                name="counselor_counselorcourse_import_word_preview",
            ),
            path(
                "import-word/done/",
                self.admin_site.admin_view(self.import_word_done_view),
                name="counselor_counselorcourse_import_word_done",
            ),
            path(
                "delete-confirm/",
                self.admin_site.admin_view(self.delete_courses_view),
                name="counselor_counselorcourse_delete_confirm",
            ),
        ]
        return custom + super().get_urls()

    def import_word_view(self, request):
        from counselor.word_course_admin import import_word
        return import_word(self, request)

    def import_word_preview_view(self, request):
        from counselor.word_course_admin import import_word_preview
        return import_word_preview(self, request)

    def import_word_done_view(self, request):
        from counselor.word_course_admin import import_word_done
        return import_word_done(self, request)

    def view_on_site(self, obj):
        if not obj or not obj.title:
            return None
        return reverse("counselor:course_overview", kwargs={"course_name": obj.title})

    @admin.display(description="Default flag")
    def default_logo_preview(self, obj):
        from counselor.builtin_images import flag_asset
        if not obj or not (obj.title or "").strip():
            return "Enter a course name and save to see the default flag."
        return _default_asset_preview(flag_asset(obj.title), "No built-in flag for this course name.")

    @admin.display(description="Default overview image")
    def default_overview_preview(self, obj):
        from counselor.builtin_images import overview_asset
        if not obj or not (obj.title or "").strip():
            return "Enter a course name and save to see the default overview image."
        return _default_asset_preview(overview_asset(obj.title), "No default overview image for this course name.")

    @admin.display(description="Preview")
    def course_preview(self, obj):
        if not obj.title:
            return ""
        url = reverse("counselor:course_overview", kwargs={"course_name": obj.title})
        return format_html('<a href="{}" target="_blank">Preview</a>', url)

    def delete_view(self, request, object_id, extra_context=None):
        course = self.get_object(request, object_id)
        if course is None:
            return self._get_obj_does_not_exist_redirect(request, self.model._meta, object_id)
        return self._confirm_course_delete(request, [course])

    def delete_course_and_files(self, request, queryset):
        ids = [str(pk) for pk in queryset.values_list("pk", flat=True)]
        request.session["course_delete_ids"] = ids
        request.session.modified = True
        return redirect("admin:counselor_counselorcourse_delete_confirm")

    delete_course_and_files.short_description = "Delete selected courses and their files"

    def delete_courses_view(self, request):
        ids = request.POST.getlist("course_ids") or request.session.get("course_delete_ids") or []
        courses = list(self.get_queryset(request).filter(pk__in=ids))
        if not courses:
            self.message_user(request, "Select a course before deleting.", level=messages.WARNING)
            return redirect("admin:counselor_counselorcourse_changelist")
        return self._confirm_course_delete(request, courses)

    def _confirm_course_delete(self, request, courses):
        from django.core.exceptions import PermissionDenied
        from counselor.course_delete import course_delete_summary, delete_courses, phrases_match

        for course in courses:
            if not self.has_delete_permission(request, course):
                raise PermissionDenied
        banner = ""
        if request.method == "POST" and "confirm_text" in request.POST:
            posted_ids = {str(pk) for pk in request.POST.getlist("course_ids")}
            selected_ids = {str(course.pk) for course in courses}
            if posted_ids != selected_ids:
                banner = "The confirmation did not match the courses on this page. Start the delete again."
            elif not phrases_match(courses, request.POST.get("confirm_text") or ""):
                banner = "Type the course title exactly. Nothing was deleted."
            else:
                result = delete_courses(courses)
                request.session.pop("course_delete_ids", None)
                names = ", ".join((course.title or "untitled-%s" % course.pk) for course in courses)
                detail = "Deleted %s." % names
                if result["removed_files"]:
                    detail += " Removed files: %s." % ", ".join(result["removed_files"])
                if result["failed_files"]:
                    detail += " Some files could not be removed: %s." % ", ".join(result["failed_files"])
                self.message_user(request, detail, level=messages.SUCCESS)
                return redirect("admin:counselor_counselorcourse_changelist")
        context = {
            **self.admin_site.each_context(request),
            "title": "Delete course",
            "opts": self.model._meta,
            "courses": courses,
            "summaries": [course_delete_summary(course) for course in courses],
            "banner": banner,
            "cancel_url": reverse("admin:counselor_counselorcourse_changelist"),
        }
        return TemplateResponse(request, "admin/counselor/counselorcourse/delete_course.html", context)

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
    list_display = ('course', 'intro_preview', 'closing_preview')
    search_fields = ('course__title',)
    list_filter = ('course',)
    list_select_related = ('course',)

    def get_form(self, request, obj=None, **kwargs):
        class OverviewSummaryForm(forms.ModelForm):
            title1 = forms.CharField(label="Introduction", widget=CKEditorWidget(), required=False)
            title2 = forms.CharField(label="Closing", widget=CKEditorWidget(), required=False)

            class Meta:
                model = CourseOverviewSummary
                fields = '__all__'

        kwargs['form'] = OverviewSummaryForm
        return super().get_form(request, obj, **kwargs)

    @admin.display(description="Introduction")
    def intro_preview(self, obj):
        return _overview_plain(obj.title1)

    @admin.display(description="Closing")
    def closing_preview(self, obj):
        return _overview_plain(obj.title2)

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

