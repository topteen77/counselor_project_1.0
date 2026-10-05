"""Admin pages for importing a counsellor course from Word files on this computer."""
from __future__ import annotations

import json
from pathlib import Path

from django.contrib import messages
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

PRODUCTION_HOST = "43.205.138.85"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "course_import" / "output"
DEFAULT_FOLDER = "/home/itpc6/Public/share/arvinder/counsellor course/China"
SESSION_FILE = "word_course_import_file"
SESSION_RESULT = "word_course_import_result"


def _store_path(request) -> Path:
    if not request.session.session_key:
        request.session.save()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / ("admin-%s.json" % request.session.session_key)


def _load_job(request):
    path = request.session.get(SESSION_FILE)
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    try:
        file_path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return None
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_job(request, job):
    path = _store_path(request)
    path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    request.session[SESSION_FILE] = str(path)
    request.session.modified = True


def _importer():
    from course_import.convert import convert_folder
    from course_import.dbimport import CourseImportError, write_course
    return convert_folder, CourseImportError, write_course


def import_word(modeladmin, request):
    try:
        convert_folder, course_import_error, write_course = _importer()
    except ImportError:
        messages.error(
            request,
            "The Word importer is not available on this server. The course_import folder must sit next to the project.",
        )
        return redirect("admin:counselor_counselorcourse_changelist")

    host = (connection.settings_dict.get("HOST") or "").strip()
    if host == PRODUCTION_HOST:
        messages.error(
            request,
            "This admin is connected to the production database. Course import is only allowed on the local site.",
        )
        return redirect("admin:counselor_counselorcourse_changelist")

    job = _load_job(request) or {}
    action = request.POST.get("action") or ""
    banner = ""
    banner_ok = False
    step = 1

    if request.method == "POST" and action == "analyze":
        payload = convert_folder(
            (request.POST.get("folder") or "").strip(),
            remove_blank_paragraphs=request.POST.get("remove_blank_paragraphs") == "on",
            remove_blank_lines=request.POST.get("remove_blank_lines") == "on",
        )
        job = {
            "payload": payload,
            "config": {
                "country": payload.get("country_guess") or "",
                "display_title": payload.get("display_title_guess") or "",
                "price": "0",
                "intro_html": payload.get("intro_html") or "",
                "conclusion_html": payload.get("conclusion_html") or "",
                "replace_existing": False,
            },
        }
        job["settings_saved"] = False
        job["step"] = 2 if payload.get("ready") else 1
        _save_job(request, job)
        request.session.pop(SESSION_RESULT, None)
        step = job["step"]
    elif request.method == "POST" and action == "configure":
        if not (job.get("payload") or {}).get("ready"):
            banner = "Read the Word folder successfully before saving settings."
            step = 1
        else:
            job["config"] = {
                "country": (request.POST.get("country") or "").strip(),
                "display_title": (request.POST.get("display_title") or "").strip(),
                "price": (request.POST.get("price") or "0").strip(),
                "intro_html": request.POST.get("intro_html") or "",
                "conclusion_html": request.POST.get("conclusion_html") or "",
                "replace_existing": request.POST.get("replace_existing") == "on",
            }
            job["settings_saved"] = True
            job["step"] = 3
            _save_job(request, job)
            step = 3
    elif request.method == "POST" and action == "import":
        step = 3
        if not (job.get("payload") or {}).get("ready") or not (job.get("config") or {}).get("country"):
            banner = "Save the course settings before importing."
            step = 2
        else:
            config = dict(job["config"])
            config["replace_existing"] = request.POST.get("replace_existing") == "on"
            job["config"] = config
            _save_job(request, job)
            mode = request.POST.get("mode") or "dry"
            if mode == "apply" and request.POST.get("confirm_write") != "on":
                banner = "Tick the confirmation box before Import. Dry run does not need it."
            else:
                try:
                    summary = write_course(job["payload"], config, dry_run=(mode != "apply"))
                except course_import_error as exc:
                    banner = str(exc)
                else:
                    request.session[SESSION_RESULT] = summary
                    request.session.modified = True
                    if not summary.get("dry_run"):
                        return redirect("admin:counselor_counselorcourse_import_word_done")
                    banner = summary.get("message") or "Dry run finished."
                    banner_ok = True
    elif job.get("step"):
        step = job.get("step") or 1

    payload = job.get("payload") or {}
    config = job.get("config") or {}
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Import a Word course",
        "opts": modeladmin.model._meta,
        "step": step,
        "banner": banner,
        "banner_ok": banner_ok,
        "folder": (payload.get("source_folder") or request.POST.get("folder") or DEFAULT_FOLDER),
        "remove_blank_paragraphs": (payload.get("options") or {}).get("remove_blank_paragraphs", True),
        "remove_blank_lines": (payload.get("options") or {}).get("remove_blank_lines", True),
        "payload": payload,
        "config": config,
        "errors": (payload.get("errors") or [])[:200],
        "warnings": (payload.get("warnings") or [])[:200],
        "stats": payload.get("stats") or {},
        "result": request.session.get(SESSION_RESULT) or {},
        "settings_saved": bool(job.get("settings_saved")),
    }
    return TemplateResponse(request, "admin/counselor/counselorcourse/import_word.html", context)


def import_word_preview(modeladmin, request):
    job = _load_job(request)
    payload = (job or {}).get("payload") or {}
    if not payload:
        return HttpResponse("Convert a folder before opening the preview.", status=404, content_type="text/plain")
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Converted course</title>",
        "<style>body{font-family:Georgia,serif;max-width:880px;margin:24px auto;line-height:1.55;padding:0 16px}",
        "table{border-collapse:collapse;width:100%;margin:12px 0}td,th{border:1px solid #ccc;padding:6px;vertical-align:top}",
        ".quiz{background:#f6f7f9;padding:12px 16px;border-radius:8px}</style></head><body>",
    ]
    from django.utils.html import escape
    for chapter in payload.get("chapters") or []:
        parts.append("<h2>%s</h2>" % escape(chapter.get("title")))
        for part in chapter.get("parts") or []:
            parts.append("<h3>%s</h3>" % escape(part.get("title")))
            parts.append(part.get("html") or "")
            quiz = part.get("quiz")
            if not quiz:
                continue
            parts.append("<div class='quiz'><strong>%s</strong><ol>" % escape(quiz.get("title")))
            for question in quiz.get("questions") or []:
                parts.append("<li>%s<ul>" % escape(question.get("text")))
                for answer in question.get("answers") or []:
                    mark = " (correct)" if answer.get("correct") else ""
                    parts.append("<li>%s%s</li>" % (escape(answer.get("text")), mark))
                parts.append("</ul></li>")
            parts.append("</ol></div>")
    parts.append("</body></html>")
    return HttpResponse("".join(parts))


def import_word_done(modeladmin, request):
    summary = request.session.get(SESSION_RESULT) or {}
    if not summary or summary.get("dry_run"):
        return redirect("admin:counselor_counselorcourse_import_word")
    course_id = summary.get("course_id")
    title = summary.get("course_title") or ""
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Course imported",
        "opts": modeladmin.model._meta,
        "summary": summary,
        "overview_url": reverse("counselor:course_overview", kwargs={"course_name": title}),
        "player_url": reverse("counselor:counselor_enrolled_course_param", kwargs={"course_name": title}),
        "admin_url": reverse("admin:counselor_counselorcourse_change", args=[course_id]) if course_id else "",
        "list_url": reverse("admin:counselor_counselorcourse_changelist"),
        "site_url": "/",
    }
    return TemplateResponse(request, "admin/counselor/counselorcourse/import_word_done.html", context)
