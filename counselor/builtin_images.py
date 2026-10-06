"""Copy the built-in flag and overview photo onto a course when those fields are empty."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files import File

FLAG_FILES = {
    "germany": "icef-germany-flag.svg",
    "uk": "icef-uk-flag.svg",
    "usa": "icef-usa-flag.svg",
    "singapore": "icef-singapore-flag.svg",
    "newzealand": "icef-nz-flag.svg",
    "ireland": "icef-ireland-flag.svg",
    "france": "icef-france-flag.svg",
    "dubai": "icef-dubai-flag.svg",
    "canada": "icef-canada-flag.svg",
    "australia": "icef-australia-flag.svg",
}


def course_key(title: str) -> str:
    return (title or "").strip().lower().replace(" ", "")


def _static_roots() -> list[Path]:
    roots = []
    for item in getattr(settings, "STATICFILES_DIRS", []) or []:
        roots.append(Path(item))
    static_root = getattr(settings, "STATIC_ROOT", None)
    if static_root:
        roots.append(Path(static_root))
    base = getattr(settings, "BASE_DIR", None)
    if base:
        roots.append(Path(base) / "static")
    unique = []
    seen = set()
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen or not resolved.is_dir():
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _find_file(*relative_parts: str) -> Path | None:
    relative = Path(*relative_parts)
    for root in _static_roots():
        path = root / relative
        if path.is_file():
            return path
    return None


def find_flag(title: str) -> Path | None:
    filename = FLAG_FILES.get(course_key(title))
    if not filename:
        return None
    return _find_file("topteenfrontend", "assets", "images", filename)


def flag_asset(title: str):
    """Relative path of the built-in flag, or None when this country has no flag file."""
    filename = FLAG_FILES.get(course_key(title))
    if not filename:
        return None
    return {
        "relative": "static/topteenfrontend/assets/images/%s" % filename,
        "static_name": "topteenfrontend/assets/images/%s" % filename,
        "exists": find_flag(title) is not None,
    }


def overview_asset(title: str):
    """Relative path of the overview photo named after the course."""
    title = (title or "").strip()
    if not title or title in (".", "..") or "/" in title or "\\" in title:
        return None
    photo = find_overview_image(title)
    filename = photo.name if photo else "%s.png" % title
    return {
        "relative": "static/topteenfrontend/assets/images/course_overview/%s" % filename,
        "static_name": "topteenfrontend/assets/images/course_overview/%s" % filename,
        "exists": photo is not None,
    }


def find_overview_image(title: str) -> Path | None:
    key = course_key(title)
    if not key:
        return None
    for root in _static_roots():
        folder = root / "topteenfrontend" / "assets" / "images" / "course_overview"
        if not folder.is_dir():
            continue
        for path in folder.iterdir():
            if path.suffix.lower() != ".png":
                continue
            if path.stem.lower().replace(" ", "") == key:
                return path
    return None


def attach_builtin_images(course) -> list[str]:
    """Save the matching static files onto empty image fields. Returns the fields filled."""
    filled = []
    if not course.logo:
        flag = find_flag(course.title)
        if flag:
            with flag.open("rb") as handle:
                course.logo.save(flag.name, File(handle), save=False)
            filled.append("logo")
    if not course.overview_image:
        photo = find_overview_image(course.title)
        if photo:
            with photo.open("rb") as handle:
                course.overview_image.save(photo.name, File(handle), save=False)
            filled.append("overview_image")
    if filled:
        course.save(update_fields=filled)
    return filled


def import_builtin_images() -> list[tuple[str, list[str]]]:
    from counselor.models import CounselorCourse

    results = []
    for course in CounselorCourse.objects.all().order_by("title"):
        results.append((course.title, attach_builtin_images(course)))
    return results
