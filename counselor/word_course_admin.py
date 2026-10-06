"""Admin pages for importing a counsellor course from Word files on this computer."""
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "course_import" / "output"
DEFAULT_FOLDER = "/home/itpc6/Public/share/arvinder/counsellor course/China"
SESSION_FILE = "word_course_import_file"
SESSION_RESULT = "word_course_import_result"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def _logo_path(request) -> Path:
    if not request.session.session_key:
        request.session.save()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return OUTPUT_DIR / ("logo-%s" % request.session.session_key)


def _store_logo(request, upload):
    name = _safe_filename(upload.name)
    ext = Path(name).suffix.lower()
    if ext not in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "The country flag must be an SVG, PNG, JPG, WEBP, or GIF file."
    dest = _logo_path(request).with_suffix(ext)
    for old in OUTPUT_DIR.glob("logo-%s.*" % request.session.session_key):
        if old != dest:
            old.unlink(missing_ok=True)
    problem = _write_upload(upload, dest)
    if problem:
        return problem
    return dest


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


def _safe_filename(name: str) -> str:
    cleaned = (name or "").replace("\\", "/").strip()
    parts = [part for part in Path(cleaned).parts if part not in ("", ".", "..") and not part.startswith("/")]
    if not parts:
        return ""
    return parts[-1]


def _course_root(folder: Path) -> Path:
    if any(folder.glob("*.docx")):
        return folder
    for child in sorted(folder.iterdir()):
        if not child.is_dir() or child.name.startswith(".") or child.name == "__MACOSX":
            continue
        if any(child.glob("*.docx")):
            return child
    return folder


def _write_upload(upload, dest: Path) -> str | None:
    written = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as handle:
        for chunk in upload.chunks():
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                return "The upload is larger than 200 MB."
            handle.write(chunk)
    return None


def _extract_zip(zip_path: Path, dest: Path) -> str | None:
    try:
        archive = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        return "The uploaded file is not a valid zip archive."
    total = 0
    with archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            raw_name = info.filename.replace("\\", "/")
            parts = [part for part in Path(raw_name).parts if part not in ("", ".", "..")]
            if not parts or raw_name.startswith("/") or any(part.startswith("/") for part in parts):
                return "The zip contains an unsafe path and was not extracted."
            if not parts[-1].lower().endswith(".docx"):
                continue
            total += info.file_size
            if total > MAX_UPLOAD_BYTES:
                return "The zip expands to more than 200 MB."
            target = dest.joinpath(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)
    return None


def _prepare_upload(uploads) -> tuple[str | None, Path | None, str | None]:
    chosen = [item for item in uploads if item and getattr(item, "name", "")]
    if not chosen:
        return None, None, "Choose Word files or a zip from your computer, or enter a folder path on the server."
    temp_root = Path(tempfile.mkdtemp(prefix="word-course-"))
    try:
        if len(chosen) == 1 and chosen[0].name.lower().endswith(".zip"):
            zip_path = temp_root / "upload.zip"
            problem = _write_upload(chosen[0], zip_path)
            if problem:
                return None, temp_root, problem
            problem = _extract_zip(zip_path, temp_root / "course")
            zip_path.unlink(missing_ok=True)
            if problem:
                return None, temp_root, problem
            course_dir = _course_root(temp_root / "course")
        else:
            saved = 0
            for upload in chosen:
                name = _safe_filename(upload.name)
                if not name.lower().endswith(".docx"):
                    continue
                problem = _write_upload(upload, temp_root / name)
                if problem:
                    return None, temp_root, problem
                saved += 1
            if not saved:
                return None, temp_root, "Upload Word .docx files, or one .zip of a single country folder."
            course_dir = temp_root
        if not any(course_dir.glob("*.docx")):
            return None, temp_root, "No Word files were found in the upload."
        return str(course_dir), temp_root, None
    except OSError:
        return None, temp_root, "The uploaded files could not be saved for conversion."


def _attach_logo(course_id, logo_path):
    if not course_id or not logo_path:
        return
    path = Path(logo_path)
    try:
        path.resolve().relative_to(OUTPUT_DIR.resolve())
    except ValueError:
        return
    if not path.is_file():
        return
    from django.core.files import File
    from counselor.models import CounselorCourse
    course = CounselorCourse.objects.filter(pk=course_id).first()
    if course is None:
        return
    with path.open("rb") as handle:
        course.logo.save(path.name, File(handle), save=True)


def _importer():
    from course_import.convert import convert_folder
    from course_import.dbimport import CourseImportError, write_course
    return convert_folder, CourseImportError, write_course


def import_word(modeladmin, request):
    try:
        convert_folder, course_import_error, write_course = _importer()
    except ImportError as exc:
        missing = getattr(exc, "name", "") or ""
        if missing == "docx" or "docx" in str(exc):
            messages.error(
                request,
                "The Word importer needs the python-docx package on this server. Install the project requirements and try again.",
            )
        else:
            messages.error(
                request,
                "The Word importer code is not on this server. Deploy the course_import folder with the project and try again.",
            )
        return redirect("admin:counselor_counselorcourse_changelist")

    job = _load_job(request) or {}
    action = request.POST.get("action") or ""
    banner = ""
    banner_ok = False
    step = 1

    if request.method == "POST" and action == "analyze":
        uploads = request.FILES.getlist("course_files")
        posted_folder = (request.POST.get("folder") or "").strip()
        remove_blank_paragraphs = request.POST.get("remove_blank_paragraphs") == "on"
        remove_blank_lines = request.POST.get("remove_blank_lines") == "on"
        temp_root = None
        payload = None
        try:
            if uploads:
                course_dir, temp_root, problem = _prepare_upload(uploads)
                if problem:
                    banner = problem
                else:
                    payload = convert_folder(
                        course_dir,
                        remove_blank_paragraphs=remove_blank_paragraphs,
                        remove_blank_lines=remove_blank_lines,
                    )
                    payload["source_folder"] = "Uploaded from this computer"
                    guess = payload.get("country_guess") or ""
                    if guess.startswith("word-course-"):
                        payload["country_guess"] = ""
                        payload["display_title_guess"] = ""
            elif not posted_folder:
                banner = "Upload the Word files from your computer, or enter a folder path on the server."
            else:
                payload = convert_folder(
                    posted_folder,
                    remove_blank_paragraphs=remove_blank_paragraphs,
                    remove_blank_lines=remove_blank_lines,
                )
        finally:
            if temp_root is not None:
                shutil.rmtree(temp_root, ignore_errors=True)
        if payload is not None:
            if not payload.get("ready"):
                first = (payload.get("errors") or [{}])[0]
                banner = first.get("message") or "The Word files could not be converted."
                if uploads:
                    banner = "%s The uploaded files were deleted." % banner
            elif uploads:
                banner = ""
                banner_ok = False
            job = {
                "payload": payload,
                "folder_input": posted_folder,
                "files_removed": bool(uploads),
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
        else:
            if uploads and "deleted" not in banner:
                banner = "%s The uploaded files were deleted." % banner
            job = {"folder_input": posted_folder, "step": 1, "files_removed": bool(uploads)}
            _save_job(request, job)
            step = 1
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
            logo = request.FILES.get("logo")
            if logo:
                stored = _store_logo(request, logo)
                if isinstance(stored, str):
                    banner = stored
                    job["settings_saved"] = False
                    job["step"] = 2
                else:
                    job["logo_path"] = str(stored)
                    job["logo_name"] = _safe_filename(logo.name)
            _save_job(request, job)
            step = job["step"]
    elif request.method == "POST" and action == "back":
        target = 2 if request.POST.get("to") == "2" and (job.get("payload") or {}).get("ready") else 1
        job["step"] = target
        if target < 3:
            job["settings_saved"] = False
        _save_job(request, job)
        step = target
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
                        _attach_logo(summary.get("course_id"), job.get("logo_path"))
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
        "folder": job.get("folder_input", DEFAULT_FOLDER),
        "files_removed": bool(job.get("files_removed")),
        "remove_blank_paragraphs": (payload.get("options") or {}).get("remove_blank_paragraphs", True),
        "remove_blank_lines": (payload.get("options") or {}).get("remove_blank_lines", True),
        "payload": payload,
        "config": config,
        "errors": (payload.get("errors") or [])[:200],
        "warnings": (payload.get("warnings") or [])[:200],
        "stats": payload.get("stats") or {},
        "result": request.session.get(SESSION_RESULT) or {},
        "settings_saved": bool(job.get("settings_saved")),
        "logo_name": job.get("logo_name") or "",
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
        "preview_url": reverse("admin:counselor_counselorcourse_import_word_preview"),
        "player_url": reverse("counselor:counselor_enrolled_course_param", kwargs={"course_name": title}),
        "admin_url": reverse("admin:counselor_counselorcourse_change", args=[course_id]) if course_id else "",
        "list_url": reverse("admin:counselor_counselorcourse_changelist"),
        "site_url": "/",
    }
    return TemplateResponse(request, "admin/counselor/counselorcourse/import_word_done.html", context)
