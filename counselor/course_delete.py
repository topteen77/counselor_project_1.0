"""Delete a counsellor course and the files stored for it."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction

from counselor.models import (
    Chapter,
    CounselorCertification,
    CourseContentProgress,
    CourseOverviewSummary,
    CoursePayment,
    CourseTrialStart,
    Part,
    PaymentReceipt,
    Question,
    Quiz,
    QuizAnswers,
    QuizResults,
    UserProgressTrack,
    UserQuizAttemptTrack,
)


def confirmation_phrase(course) -> str:
    title = (course.title or "").strip()
    if title:
        return title
    return "untitled-%s" % course.pk


def phrases_match(courses, typed: str) -> bool:
    expected = sorted(confirmation_phrase(course) for course in courses)
    entered = sorted(line.strip() for line in (typed or "").splitlines() if line.strip())
    return entered == expected


def overview_image_paths(title: str) -> list[Path]:
    title = (title or "").strip()
    if not title or title in (".", "..") or "/" in title or "\\" in title:
        return []
    roots = []
    for item in getattr(settings, "STATICFILES_DIRS", []) or []:
        roots.append(Path(item))
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        roots.append(Path(static_root))
    base = getattr(settings, "BASE_DIR", None)
    if base:
        roots.append(Path(base) / "static")
    relative = Path("topteenfrontend") / "assets" / "images" / "course_overview" / ("%s.png" % title)
    found = []
    seen = set()
    for root in roots:
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        path = (root_resolved / relative).resolve()
        try:
            path.relative_to(root_resolved)
        except ValueError:
            continue
        key = str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        found.append(path)
    return found


def course_delete_summary(course) -> dict:
    parts = Part.objects.filter(chapter__course=course)
    quizzes = Quiz.objects.filter(quiz_part__chapter__course=course)
    questions = Question.objects.filter(quiz__quiz_part__chapter__course=course)
    answers = QuizAnswers.objects.filter(question__quiz__quiz_part__chapter__course=course)
    receipts = PaymentReceipt.objects.filter(payment__course=course)
    images = overview_image_paths(course.title)
    receipt_files = [receipt.invoice_pdf.name for receipt in receipts if receipt.invoice_pdf]
    return {
        "course": course,
        "phrase": confirmation_phrase(course),
        "chapters": Chapter.objects.filter(course=course).count(),
        "parts": parts.count(),
        "quizzes": quizzes.count(),
        "questions": questions.count(),
        "answers": answers.count(),
        "progress": CourseContentProgress.objects.filter(part_id__chapter__course=course).count(),
        "results": QuizResults.objects.filter(course=course).count(),
        "certificates": CounselorCertification.objects.filter(course=course).count(),
        "tracks": UserProgressTrack.objects.filter(course=course).count(),
        "attempts": UserQuizAttemptTrack.objects.filter(course=course).count(),
        "trials": CourseTrialStart.objects.filter(course=course).count(),
        "payments": CoursePayment.objects.filter(course=course).count(),
        "receipts": receipts.count(),
        "overview_files": [path.name for path in images],
        "receipt_files": receipt_files,
        "summaries": CourseOverviewSummary.objects.filter(course=course).count(),
    }


def delete_courses(courses) -> dict:
    courses = list(courses)
    receipt_names = []
    image_paths = []
    for course in courses:
        for receipt in PaymentReceipt.objects.filter(payment__course=course):
            if receipt.invoice_pdf:
                receipt_names.append(receipt.invoice_pdf.name)
        image_paths.extend(overview_image_paths(course.title))
    with transaction.atomic():
        for course in courses:
            course.delete()
    removed = []
    failed = []
    for name in receipt_names:
        try:
            default_storage.delete(name)
            removed.append(name)
        except OSError:
            failed.append(name)
    for path in image_paths:
        try:
            path.unlink()
            removed.append(path.name)
        except OSError:
            failed.append(path.name)
    return {"removed_files": removed, "failed_files": failed, "courses": len(courses)}
