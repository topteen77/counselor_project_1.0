"""Local four-step wizard for converting counsellor Word courses and loading them.

Run from the project root:

    python course_import/wizard.py

Then open http://127.0.0.1:8765/

Check a folder without starting the wizard:

    python course_import/wizard.py --check "/path/to/China"

This process listens only on localhost. It will not write to the production database.
The course_import folder is gitignored.
"""
from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from course_import.convert import convert_folder
from course_import.dbimport import LOCAL_DB_HOSTS, CourseImportError, run_import

OUTPUT = Path(__file__).resolve().parent / "output"
SESSION = OUTPUT / "session.json"
PREVIEW = OUTPUT / "preview.html"
HOST = "127.0.0.1"
PORT = int(os.environ.get("COURSE_IMPORT_PORT", "8765"))
DEFAULT_FOLDER = "/home/itpc6/Public/share/arvinder/counsellor course/China"


def _checked(value) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


def _load() -> dict:
    if not SESSION.exists():
        return {}
    try:
        return json.loads(SESSION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    SESSION.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


DOCKER_WEB = "counselor_local_web"


def _docker_web_running() -> bool:
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return DOCKER_WEB in result.stdout.split()


def _run_in_docker(payload, config, dry_run) -> dict:
    if not _docker_web_running():
        raise CourseImportError(
            "The local site container %s is not running. Start it with ./deploy.sh start, "
            "or untick Docker and enter a MySQL database that is listening on this computer."
            % DOCKER_WEB
        )
    request = {"payload": payload, "config": config, "dry_run": dry_run}
    try:
        result = subprocess.run(
            ["docker", "exec", "-i", DOCKER_WEB, "python", "course_import/import_stdin.py"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CourseImportError("Could not run the import inside Docker: %s" % exc)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "The Docker import failed.").strip()
        raise CourseImportError(detail[-800:])
    lines = [line for line in result.stdout.splitlines() if line.startswith("{") and line.endswith("}")]
    if not lines:
        raise CourseImportError("The Docker import did not return a result. %s" % (result.stderr or "")[-400:])
    return json.loads(lines[-1])


def _db_prefill() -> dict:
    host = (os.environ.get("DB_HOST") or os.environ.get("COURSE_IMPORT_DB_HOST") or "127.0.0.1").strip()
    local = host.lower() in LOCAL_DB_HOSTS
    return {
        "host": host if local else "127.0.0.1",
        "port": os.environ.get("DB_PORT") or os.environ.get("COURSE_IMPORT_DB_PORT") or "3306",
        "name": (os.environ.get("DB_NAME") or os.environ.get("COURSE_IMPORT_DB_NAME") or "counselor_course") if local else "counselor_course",
        "user": (os.environ.get("DB_USER") or os.environ.get("COURSE_IMPORT_DB_USER") or "counselor") if local else "counselor",
        "password": (os.environ.get("DB_PASSWORD") or os.environ.get("COURSE_IMPORT_DB_PASSWORD") or "") if local else "",
        "base_url": os.environ.get("COURSE_IMPORT_APP_URL", "http://127.0.0.1:8000"),
        "use_docker": _docker_web_running(),
    }


def _issues_html(items, empty_text):
    if not items:
        return "<p class='muted'>%s</p>" % _esc(empty_text)
    rows = []
    shown = items[:200]
    for item in shown:
        where = " / ".join(part for part in (item.get("filename"), item.get("location")) if part)
        rows.append("<li><strong>%s</strong> %s</li>" % (_esc(where or "Course"), _esc(item.get("message"))))
    extra = ""
    if len(items) > len(shown):
        extra = "<p>%s more are not shown. Fix these and run step 1 again.</p>" % (len(items) - len(shown))
    return "<ul class='issues'>%s</ul>%s" % ("".join(rows), extra)


def _layout(title, step, body, banner=""):
    steps = ["1. Read Word files", "2. Course settings", "3. Import", "4. Preview"]
    chips = []
    for index, label in enumerate(steps, start=1):
        klass = "chip current" if index == step else "chip"
        chips.append("<span class='%s'>%s</span>" % (klass, _esc(label)))
    banner_html = "<div class='banner'>%s</div>" % banner if banner else ""
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%s</title>
<style>
body { margin: 0; font-family: "Segoe UI", sans-serif; background: #f4f6f8; color: #1c2430; }
main { max-width: 980px; margin: 0 auto; padding: 28px 20px 60px; }
h1 { font-size: 28px; margin: 0 0 8px; }
h2 { font-size: 20px; margin: 28px 0 10px; }
.note { color: #526072; margin-top: 0; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 18px 0; }
.chip { background: #e7edf3; border-radius: 999px; padding: 6px 12px; font-size: 14px; }
.chip.current { background: #1f6feb; color: white; }
.card { background: white; border: 1px solid #d8e0e8; border-radius: 12px; padding: 18px; margin-top: 16px; }
label { display: block; font-weight: 600; margin: 14px 0 6px; }
input[type=text], input[type=password], input[type=number], textarea { width: 100%%; box-sizing: border-box; border: 1px solid #c5d0db; border-radius: 8px; padding: 10px; font: inherit; }
textarea { min-height: 140px; font-family: Consolas, monospace; font-size: 13px; }
.editor-tools { display: flex; gap: 6px; margin-bottom: 6px; }
.editor-tools button { background: #e7edf3; color: #1c2430; margin: 0; padding: 6px 10px; }
.text-editor { min-height: 220px; max-height: 420px; overflow: auto; border: 1px solid #c5d0db; border-radius: 8px; padding: 12px 14px; line-height: 1.55; background: #fff; }
.text-editor:focus { outline: 2px solid #1f6feb; }
.text-editor p { margin: 0 0 10px; }
.check { font-weight: 500; }
button, .button { background: #1f6feb; color: white; border: 0; border-radius: 8px; padding: 10px 16px; font: inherit; text-decoration: none; display: inline-block; margin: 8px 8px 0 0; cursor: pointer; }
button.secondary, .button.secondary { background: #526072; }
button.warn { background: #9a3412; }
.stats { display: flex; flex-wrap: wrap; gap: 10px; }
.stat { background: #f4f7fb; border-radius: 8px; padding: 10px 12px; min-width: 110px; }
.stat b { display: block; font-size: 20px; }
.issues { padding-left: 18px; }
.issues li { margin: 6px 0; }
.error { background: #fde8e8; border: 1px solid #f3b4b4; padding: 12px; border-radius: 8px; }
.warnbox { background: #fff7e8; border: 1px solid #f0d7a2; padding: 12px; border-radius: 8px; }
.ok { background: #e8f7ee; border: 1px solid #b7e4c7; padding: 12px; border-radius: 8px; }
.banner { margin: 12px 0; }
.muted { color: #66788a; }
</style>
</head>
<body>
<main>
<h1>Course import wizard</h1>
<p class="note">Local tool only. Word files are converted on this computer, and the database step refuses the production server. This folder is not part of the deployed site.</p>
<div class="chips">%s</div>
%s
%s
</main>
</body>
</html>""" % (_esc(title), "".join(chips), banner_html, body)


def _write_preview(payload: dict):
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Course preview</title>",
        "<style>body{font-family:Georgia,serif;max-width:880px;margin:24px auto;line-height:1.55;padding:0 16px}",
        "table{border-collapse:collapse;width:100%;margin:12px 0}td,th{border:1px solid #ccc;padding:6px;vertical-align:top}",
        "h2{margin-top:2.2rem} .quiz{background:#f6f7f9;padding:12px 16px;border-radius:8px}</style></head><body>",
        "<p>This is the converted lesson HTML. It is not the live course page.</p>",
    ]
    for chapter in payload.get("chapters") or []:
        parts.append("<h2>%s</h2>" % _esc(chapter.get("title")))
        parts.append("<p class='muted'>Source: %s</p>" % _esc(chapter.get("source_file")))
        for part in chapter.get("parts") or []:
            parts.append("<h3>%s</h3>" % _esc(part.get("title")))
            parts.append(part.get("html") or "<p><em>No lesson text</em></p>")
            quiz = part.get("quiz")
            if not quiz:
                continue
            parts.append("<div class='quiz'><strong>%s</strong><ol>" % _esc(quiz.get("title")))
            for question in quiz.get("questions") or []:
                parts.append("<li>%s<ul>" % _esc(question.get("text")))
                for answer in question.get("answers") or []:
                    mark = " (correct)" if answer.get("correct") else ""
                    parts.append("<li>%s%s</li>" % (_esc(answer.get("text")), mark))
                parts.append("</ul></li>")
            parts.append("</ol></div>")
    parts.append("</body></html>")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    PREVIEW.write_text("".join(parts), encoding="utf-8")


def _step1(data, banner=""):
    payload = data.get("payload") or {}
    options = payload.get("options") or {}
    folder = payload.get("source_folder") or DEFAULT_FOLDER
    stats = payload.get("stats") or {}
    result = ""
    if payload:
        result = """
<div class="card">
<div class="stats">
<div class="stat"><b>%s</b>modules</div>
<div class="stat"><b>%s</b>parts</div>
<div class="stat"><b>%s</b>quizzes</div>
<div class="stat"><b>%s</b>questions</div>
<div class="stat"><b>%s</b>tables</div>
</div>
<h2>Errors</h2>
%s
<h2>Warnings</h2>
%s
<p><a class="button secondary" href="/preview">Open converted HTML preview</a></p>
%s
</div>""" % (
            stats.get("modules", 0),
            stats.get("parts", 0),
            stats.get("quizzes", 0),
            stats.get("questions", 0),
            stats.get("tables", 0),
            "<div class='error'>%s</div>" % _issues_html(payload.get("errors") or [], "No errors.")
            if payload.get("errors")
            else "<div class='ok'>No conversion errors. You can continue.</div>",
            _issues_html(payload.get("warnings") or [], "No warnings."),
            "<p><a class='button' href='/configure'>Continue to course settings</a></p>" if payload.get("ready") else
            "<p class='muted'>Fix the Word files, then run this step again. Nothing is written to the database from this step.</p>",
        )
    body = """
<div class="card">
<h2>1. Read the Word folder</h2>
<p>Choose the folder for one country. The wizard reads every <code>.docx</code> in that folder, keeps bold, italic, underline, paragraphs, lists, and tables, and builds the chapter, part, and quiz records.</p>
<form method="post" action="/analyze">
<label for="folder">Word course folder</label>
<input id="folder" name="folder" type="text" value="%s" required>
<label class="check"><input type="checkbox" name="remove_blank_paragraphs" %s> Remove blank paragraphs</label>
<label class="check"><input type="checkbox" name="remove_blank_lines" %s> Remove independent blank lines</label>
<button type="submit">Analyse and convert</button>
</form>
</div>
%s""" % (
        _esc(folder),
        "checked" if options.get("remove_blank_paragraphs", True) else "",
        "checked" if options.get("remove_blank_lines", True) else "",
        result,
    )
    return _layout("Read Word files", 1, body, banner)


def _step2(data, banner=""):
    payload = data.get("payload") or {}
    if not payload.get("ready"):
        return _step1(data, "<div class='error'>Run step 1 until it reports no errors.</div>")
    config = data.get("config") or {}
    country = config.get("country") or payload.get("country_guess") or ""
    display = config.get("display_title") or payload.get("display_title_guess") or ""
    price = config.get("price") if config.get("price") is not None else "0"
    intro = config.get("intro_html") if "intro_html" in config else payload.get("intro_html") or ""
    conclusion = config.get("conclusion_html") if "conclusion_html" in config else payload.get("conclusion_html") or ""
    body = """
<div class="card">
<h2>2. Course settings</h2>
<p>The country key is stored as the course title. The live course address uses that exact word, for example <code>/course-overview/China/</code>.</p>
<form method="post" action="/configure">
<label for="country">Country key</label>
<input id="country" name="country" type="text" value="%s" required>
<label for="display_title">Display title</label>
<input id="display_title" name="display_title" type="text" value="%s">
<label for="price">Price in INR (0 means free)</label>
<input id="price" name="price" type="text" value="%s">
<label>Overview introduction</label>
<div class="editor-tools">
<button type="button" onmousedown="event.preventDefault()" onclick="document.execCommand('bold')">Bold</button>
<button type="button" onmousedown="event.preventDefault()" onclick="document.execCommand('italic')">Italic</button>
<button type="button" onmousedown="event.preventDefault()" onclick="document.execCommand('underline')">Underline</button>
</div>
<div id="intro_editor" class="text-editor" contenteditable="true"></div>
<input type="hidden" name="intro_html" id="intro_html">
<label>Overview closing</label>
<div id="conclusion_editor" class="text-editor" contenteditable="true"></div>
<input type="hidden" name="conclusion_html" id="conclusion_html">
<button type="submit">Save settings</button>
<a class="button secondary" href="/">Back</a>
</form>
<script>
const introHtml = %s;
const conclusionHtml = %s;
document.getElementById("intro_editor").innerHTML = introHtml;
document.getElementById("conclusion_editor").innerHTML = conclusionHtml;
document.querySelector("form").addEventListener("submit", function () {
  document.getElementById("intro_html").value = document.getElementById("intro_editor").innerHTML;
  document.getElementById("conclusion_html").value = document.getElementById("conclusion_editor").innerHTML;
});
</script>
</div>""" % (
        _esc(country),
        _esc(display),
        _esc(price),
        json.dumps(intro).replace("<", "\\u003c"),
        json.dumps(conclusion).replace("<", "\\u003c"),
    )
    return _layout("Course settings", 2, body, banner)


def _step3(data, banner=""):
    payload = data.get("payload") or {}
    config = data.get("config") or {}
    if not payload.get("ready") or not config.get("country"):
        return _step2(data, "<div class='error'>Save the course settings before importing.</div>")
    db = data.get("db") or _db_prefill()
    stats = payload.get("stats") or {}
    body = """
<div class="card">
<h2>3. Import into the local database</h2>
<p>Country <strong>%s</strong>, price <strong>%s</strong>. This will write %s chapters, %s parts, %s quizzes, and %s questions.</p>
<div class="warnbox">Dry run performs the inserts and then rolls them back. Import saves them. If anything fails, the database transaction is rolled back.</div>
<form method="post" action="/import">
<label class="check"><input type="checkbox" name="use_docker" %s> Use the local Docker database inside counselor_local_web. Leave this ticked when the site was started with ./deploy.sh. Untick it only for a MySQL server on this computer.</label>
<label for="host">Database host</label>
<input id="host" name="host" type="text" value="%s" required>
<label for="port">Port</label>
<input id="port" name="port" type="text" value="%s" required>
<label for="name">Database name</label>
<input id="name" name="name" type="text" value="%s" required>
<label for="user">Database user</label>
<input id="user" name="user" type="text" value="%s" required>
<label for="password">Database password</label>
<input id="password" name="password" type="password" value="%s">
<label for="base_url">Local site address for the preview links</label>
<input id="base_url" name="base_url" type="text" value="%s">
<label class="check"><input type="checkbox" name="replace_existing" %s> Replace chapters if this country already exists. Learner progress for those chapters is cleared. Payments on the course are kept.</label>
<label class="check"><input type="checkbox" name="confirm_write"> I understand Import will write this course into the local database named above.</label>
<button class="secondary" type="submit" name="mode" value="dry">Dry run</button>
<button class="warn" type="submit" name="mode" value="apply">Import</button>
<a class="button secondary" href="/configure">Back</a>
</form>
</div>""" % (
        _esc(config.get("country")),
        _esc(config.get("price")),
        stats.get("modules", 0),
        stats.get("parts", 0),
        stats.get("quizzes", 0),
        stats.get("questions", 0),
        "checked" if db.get("use_docker", True) else "",
        _esc(db.get("host")),
        _esc(db.get("port")),
        _esc(db.get("name")),
        _esc(db.get("user")),
        _esc(db.get("password")),
        _esc(db.get("base_url")),
        "checked" if config.get("replace_existing") else "",
    )
    return _layout("Import", 3, body, banner)


def _step4(data):
    result = data.get("result") or {}
    if not result or result.get("dry_run"):
        return _step3(data, "<div class='error'>Finish an actual import before opening the preview step.</div>")
    base = (data.get("db") or {}).get("base_url") or "http://127.0.0.1:8000"
    base = base.rstrip("/")
    country = quote(result.get("course_title") or "")
    course_id = result.get("course_id")
    overview = "%s/course-overview/%s/" % (base, country)
    player = "%s/counselor_enrolled_course/%s/" % (base, country)
    admin_change = "%s/admin/counselor/counselorcourse/%s/change/" % (base, course_id)
    admin_list = "%s/admin/counselor/counselorcourse/" % base
    body = """
<div class="card">
<div class="ok"><strong>%s</strong><p>Saved %s chapters, %s parts, %s quizzes, and %s questions for %s.</p></div>
<h2>4. Open the course</h2>
<p><a class="button" href="%s">Course preview</a></p>
<p><a class="button secondary" href="%s">Course player</a> The player asks for a counsellor login.</p>
<p><a class="button secondary" href="%s">Admin course view</a></p>
<p><a class="button secondary" href="%s">All courses in admin</a></p>
<p class="muted">The catalogue page lists countries in code. A new country appears on the course overview and in admin as soon as this import succeeds. Add it to the catalogue card list when you want it on the public course grid.</p>
<p><a class="button secondary" href="/">Import another folder</a></p>
</div>""" % (
        _esc(result.get("message")),
        result.get("chapters"),
        result.get("parts"),
        result.get("quizzes"),
        result.get("questions"),
        _esc(result.get("course_title")),
        _esc(overview),
        _esc(player),
        _esc(admin_change),
        _esc(admin_list),
    )
    return _layout("Preview", 4, body)


class WizardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, content, status=200, content_type="text/html; charset=utf-8"):
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _form(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[0] for key, values in parsed.items()}

    def do_GET(self):
        path = urlparse(self.path).path
        data = _load()
        if path == "/preview":
            if not PREVIEW.exists():
                self._send(_layout("Preview", 1, "<div class='error'>Convert a folder before opening the HTML preview.</div>"), 404)
                return
            self._send(PREVIEW.read_text(encoding="utf-8"))
            return
        if path == "/configure":
            self._send(_step2(data))
            return
        if path == "/import":
            self._send(_step3(data))
            return
        if path == "/done":
            self._send(_step4(data))
            return
        self._send(_step1(data))

    def do_POST(self):
        path = urlparse(self.path).path
        form = self._form()
        data = _load()
        try:
            if path == "/analyze":
                folder = (form.get("folder") or "").strip()
                payload = convert_folder(
                    folder,
                    remove_blank_paragraphs=_checked(form.get("remove_blank_paragraphs")),
                    remove_blank_lines=_checked(form.get("remove_blank_lines")),
                )
                data["payload"] = payload
                data["config"] = {}
                data["result"] = {}
                _save(data)
                _write_preview(payload)
                self._send(_step1(data))
                return
            if path == "/configure":
                if not (data.get("payload") or {}).get("ready"):
                    self._send(_step1(data, "<div class='error'>Step 1 has errors, so settings were not saved.</div>"))
                    return
                data["config"] = {
                    "country": (form.get("country") or "").strip(),
                    "display_title": (form.get("display_title") or "").strip(),
                    "price": (form.get("price") or "0").strip(),
                    "intro_html": form.get("intro_html") or "",
                    "conclusion_html": form.get("conclusion_html") or "",
                    "replace_existing": _checked(form.get("replace_existing")),
                }
                data["result"] = {}
                _save(data)
                self._redirect("/import")
                return
            if path == "/import":
                db = {
                    "host": (form.get("host") or "").strip(),
                    "port": (form.get("port") or "3306").strip(),
                    "name": (form.get("name") or "").strip(),
                    "user": (form.get("user") or "").strip(),
                    "password": form.get("password") or "",
                    "base_url": (form.get("base_url") or "http://127.0.0.1:8000").strip(),
                    "use_docker": _checked(form.get("use_docker")),
                }
                data["db"] = db
                config = dict(data.get("config") or {})
                config["replace_existing"] = _checked(form.get("replace_existing"))
                data["config"] = config
                mode = form.get("mode") or "dry"
                if mode == "apply" and not _checked(form.get("confirm_write")):
                    _save(data)
                    self._send(_step3(data, "<div class='error'>Tick the confirmation box before Import. The dry run does not need it.</div>"))
                    return
                if db["use_docker"]:
                    summary = _run_in_docker(
                        data.get("payload") or {},
                        config,
                        dry_run=(mode != "apply"),
                    )
                else:
                    summary = run_import(
                        data.get("payload") or {},
                        config,
                        db,
                        dry_run=(mode != "apply"),
                    )
                data["result"] = summary
                _save(data)
                if summary.get("dry_run"):
                    detail = (
                        "<div class='ok'><strong>%s</strong><p>Would save %s chapters, %s parts, %s quizzes, "
                        "and %s questions on host %s.</p></div>"
                    ) % (
                        _esc(summary.get("message")),
                        summary.get("chapters"),
                        summary.get("parts"),
                        summary.get("quizzes"),
                        summary.get("questions"),
                        _esc(summary.get("database_host")),
                    )
                    if summary.get("replaced"):
                        detail += "<div class='warnbox'>Replacement would clear %s learner progress rows for this course.</div>" % summary.get("learner_rows_cleared")
                    self._send(_step3(data, detail))
                    return
                self._redirect("/done")
                return
        except CourseImportError as exc:
            _save(data)
            banner = "<div class='error'>%s</div>" % _esc(exc)
            if path == "/analyze":
                self._send(_step1(data, banner))
            elif path == "/configure":
                self._send(_step2(data, banner))
            else:
                self._send(_step3(data, banner))
            return
        except Exception as exc:
            message = str(exc)
            password = (data.get("db") or {}).get("password") or ""
            if password:
                message = message.replace(password, "***")
            banner = "<div class='error'>The step stopped. %s</div>" % _esc(message[:800])
            if path == "/analyze":
                self._send(_step1(data, banner))
            elif path == "/configure":
                self._send(_step2(data, banner))
            else:
                self._send(_step3(data, banner))
            return
        self._send(_layout("Course import", 1, "<div class='error'>Unknown action.</div>"), 404)


def check_folder(folder: str):
    payload = convert_folder(folder)
    stats = payload["stats"]
    print("Folder: %s" % payload["source_folder"])
    print(
        "modules=%s parts=%s quizzes=%s questions=%s tables=%s errors=%s warnings=%s"
        % (
            stats["modules"],
            stats["parts"],
            stats["quizzes"],
            stats["questions"],
            stats["tables"],
            stats["errors"],
            stats["warnings"],
        )
    )
    for item in (payload["errors"] + payload["warnings"])[:40]:
        print("[%s] %s %s" % (item["level"], item.get("filename") or "", item["message"][:180]))
    if stats["errors"] > 40:
        print("... %s more errors" % (stats["errors"] - 40))
    return 0 if payload["ready"] else 1


def main(argv):
    if len(argv) >= 3 and argv[1] == "--check":
        raise SystemExit(check_folder(argv[2]))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), WizardHandler)
    print("Course import wizard: http://%s:%s/" % (HOST, PORT))
    print("This wizard is local only and will not write to production.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main(sys.argv)
