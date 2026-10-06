"""Write a converted course into the local database.

Dry run uses the same inserts as a real import, then rolls the transaction back.
Any error rolls the transaction back and leaves the database unchanged.
"""
from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "db", "::1"}
BLOCKED_HOSTS = {"43.205.138.85"}
COUNTRY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]{0,40}$")


class CourseImportError(Exception):
    """The import stopped. Nothing was committed."""


def assert_local_host(host: str) -> str:
    cleaned = (host or "").strip().lower()
    if cleaned in BLOCKED_HOSTS or cleaned not in LOCAL_DB_HOSTS:
        raise CourseImportError(
            "Import blocked for database host %r. This tool only writes to a local database "
            "(localhost, 127.0.0.1, ::1, or the Docker host name db). "
            "It will not write to the production server." % (host or "")
        )
    return cleaned


def parse_price(value) -> Decimal:
    text = str(value if value is not None else "").strip()
    if text == "":
        text = "0"
    try:
        price = Decimal(text)
    except InvalidOperation:
        raise CourseImportError("Price must be a number, for example 0 or 4999.00.")
    if price < 0:
        raise CourseImportError("Price cannot be negative.")
    if price > Decimal("99999999.99"):
        raise CourseImportError("Price is too large.")
    return price.quantize(Decimal("0.01"))


def validate_config(config: dict) -> dict:
    country = (config.get("country") or "").strip()
    if not COUNTRY_RE.match(country):
        raise CourseImportError(
            "Country key must be one word of letters and numbers, such as China or Japan. "
            "This value is the course title and the address of the course."
        )
    price = parse_price(config.get("price", "0"))
    display_title = (config.get("display_title") or "").strip()
    if len(display_title) > 200:
        raise CourseImportError("Display title is longer than 200 characters.")
    intro_html = config.get("intro_html") if config.get("intro_html") is not None else ""
    conclusion_html = config.get("conclusion_html") if config.get("conclusion_html") is not None else ""
    return {
        "country": country,
        "price": price,
        "display_title": display_title,
        "intro_html": intro_html,
        "conclusion_html": conclusion_html,
        "replace_existing": bool(config.get("replace_existing")),
    }


def _setup_django(db: dict):
    host = assert_local_host(db.get("host"))
    os.environ["COURSE_IMPORT_DB_HOST"] = host
    os.environ["COURSE_IMPORT_DB_NAME"] = (db.get("name") or "").strip()
    os.environ["COURSE_IMPORT_DB_USER"] = (db.get("user") or "").strip()
    os.environ["COURSE_IMPORT_DB_PASSWORD"] = db.get("password") or ""
    os.environ["COURSE_IMPORT_DB_PORT"] = str(db.get("port") or "3306").strip()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "course_import.django_settings")
    if not os.environ["COURSE_IMPORT_DB_NAME"]:
        raise CourseImportError("Database name is required.")
    if not os.environ["COURSE_IMPORT_DB_USER"]:
        raise CourseImportError("Database user is required.")

    import django
    from django.conf import settings
    from django.db import connections

    if not settings.configured:
        django.setup()
    from course_import.django_settings import importer_database

    local_db = importer_database()
    settings.DATABASES["default"] = local_db
    connections.close_all()
    connection = connections["default"]
    connection.settings_dict.update(local_db)
    connection.close()
    return host


def _payload_problems(payload: dict) -> list[str]:
    problems = []
    if not payload.get("ready"):
        problems.append("Step 1 still has errors. Fix the Word files and run step 1 again.")
    if not payload.get("chapters"):
        problems.append("There are no chapters to import.")
    for chapter in payload.get("chapters") or []:
        if len(chapter.get("title") or "") > 100:
            problems.append("Chapter title is too long: %s" % chapter.get("title"))
        for part in chapter.get("parts") or []:
            if len(part.get("title") or "") > 100:
                problems.append("Part title is too long: %s" % part.get("title"))
            quiz = part.get("quiz")
            if not quiz:
                continue
            for question in quiz.get("questions") or []:
                answers = question.get("answers") or []
                if len(answers) != 4:
                    problems.append("A question does not have 4 answers in %s." % part.get("title"))
                correct = [item for item in answers if item.get("correct")]
                if len(correct) != 1:
                    problems.append("A question does not have one correct answer in %s." % part.get("title"))
                for answer in answers:
                    if len(answer.get("text") or "") > 200:
                        problems.append("An answer is longer than 200 characters in %s." % part.get("title"))
    return problems


def write_course(payload: dict, config: dict, dry_run: bool, database_label: str = "this site") -> dict:
    """Insert a converted course using the database Django is already using.

    A dry run performs the inserts and then rolls the transaction back.
    """
    problems = _payload_problems(payload)
    if problems:
        raise CourseImportError(problems[0])
    cleaned = validate_config(config)

    from django.db import DatabaseError, transaction

    from counselor.models import (
        Chapter,
        CounselorCourse,
        CourseContentProgress,
        CourseOverviewSummary,
        Part,
        Question,
        Quiz,
        QuizAnswers,
        UserProgressTrack,
        UserQuizAttemptTrack,
    )

    try:
        with transaction.atomic():
            existing = CounselorCourse.objects.filter(title=cleaned["country"]).first()
            progress_rows = 0
            if existing and not cleaned["replace_existing"]:
                raise CourseImportError(
                    "A course named %s already exists. Turn on replacement to reload its chapters, "
                    "or choose a different country key." % cleaned["country"]
                )
            if existing and cleaned["replace_existing"]:
                part_ids = list(Part.objects.filter(chapter__course=existing).values_list("id", flat=True))
                progress_rows = CourseContentProgress.objects.filter(part_id__in=part_ids).count()
                progress_rows += UserProgressTrack.objects.filter(course=existing).count()
                progress_rows += UserQuizAttemptTrack.objects.filter(course=existing).count()
                Chapter.objects.filter(course=existing).delete()
                CourseOverviewSummary.objects.filter(course=existing).delete()
                existing.price = cleaned["price"]
                existing.save(update_fields=["price", "updated_at"])
                course = existing
                created = False
            else:
                course = CounselorCourse.objects.create(title=cleaned["country"], price=cleaned["price"])
                created = True

            if cleaned["intro_html"] or cleaned["conclusion_html"]:
                CourseOverviewSummary.objects.create(
                    course=course,
                    title1=cleaned["intro_html"],
                    title2=cleaned["conclusion_html"],
                )

            chapter_count = 0
            part_count = 0
            quiz_count = 0
            question_count = 0
            answer_count = 0
            for chapter_data in payload["chapters"]:
                chapter = Chapter.objects.create(
                    course=course,
                    title=chapter_data["title"],
                    index=int(chapter_data["index"]),
                )
                chapter_count += 1
                for part_data in chapter_data["parts"]:
                    part = Part.objects.create(
                        chapter=chapter,
                        title=part_data["title"],
                        description=part_data.get("html") or "",
                        index=int(part_data["index"]),
                    )
                    part_count += 1
                    quiz_data = part_data.get("quiz")
                    if not quiz_data:
                        continue
                    quiz = Quiz.objects.create(title=quiz_data.get("title") or "Quiz", quiz_part=part)
                    quiz_count += 1
                    for question_data in quiz_data.get("questions") or []:
                        question = Question.objects.create(
                            quiz=quiz,
                            question_text=question_data.get("text") or "",
                        )
                        question_count += 1
                        correct_flags = 0
                        for answer_data in question_data.get("answers") or []:
                            is_correct = bool(answer_data.get("correct"))
                            correct_flags += int(is_correct)
                            QuizAnswers.objects.create(
                                question=question,
                                answer_text=answer_data.get("text") or "",
                                is_correct=is_correct,
                            )
                            answer_count += 1
                        if correct_flags != 1:
                            raise CourseImportError("Question did not store exactly one correct answer.")

            saved_chapters = Chapter.objects.filter(course=course).count()
            if saved_chapters != chapter_count:
                raise CourseImportError("Saved chapter count does not match the converted course.")

            summary = {
                "dry_run": dry_run,
                "created": created,
                "replaced": bool(existing and cleaned["replace_existing"]),
                "course_id": course.id,
                "course_title": course.title,
                "price": str(cleaned["price"]),
                "display_title": cleaned["display_title"],
                "database_host": database_label,
                "chapters": chapter_count,
                "parts": part_count,
                "quizzes": quiz_count,
                "questions": question_count,
                "answers": answer_count,
                "learner_rows_cleared": progress_rows,
            }
            if dry_run:
                transaction.set_rollback(True)
                summary["course_id"] = None
                summary["message"] = "Dry run finished. Every insert was rolled back. Nothing was saved."
            else:
                from counselor.builtin_images import attach_builtin_images

                summary["builtin_images"] = attach_builtin_images(course)
                summary["message"] = "Course saved."
            return summary
    except CourseImportError:
        raise
    except DatabaseError as exc:
        raise CourseImportError(
            "The database rejected the import and the transaction was rolled back. %s" % _public_db_error(exc, "")
        )


def run_import(payload: dict, config: dict, db: dict, dry_run: bool) -> dict:
    host = _setup_django(db)
    try:
        return write_course(payload, config, dry_run, database_label=host)
    except CourseImportError:
        raise
    except Exception as exc:
        from django.db.utils import OperationalError
        if isinstance(exc, OperationalError):
            raise CourseImportError(
                "Could not connect to the local database. Check the host, database name, user, and password. "
                "Details: %s" % _public_db_error(exc, db.get("password"))
            )
        raise


def _public_db_error(exc, password) -> str:
    message = str(exc)
    if password:
        message = message.replace(str(password), "***")
    return message[:500]
