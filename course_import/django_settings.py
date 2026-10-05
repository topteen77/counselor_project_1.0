"""Django settings used only by the local course importer.

The database host is read from the environment at startup and must be a local
address. This module never keeps the production database selected.
"""
import os

from counselor_project.settings_local import *  # noqa: F401,F403

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "db", "::1"}


def importer_database():
    host = os.environ.get("COURSE_IMPORT_DB_HOST", "127.0.0.1").strip().lower()
    if host not in LOCAL_DB_HOSTS:
        raise RuntimeError(
            "Course import refused to use database host %r. "
            "Only localhost, 127.0.0.1, ::1, and the local Docker host 'db' are allowed."
            % host
        )
    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("COURSE_IMPORT_DB_NAME", "counselor_course"),
        "USER": os.environ.get("COURSE_IMPORT_DB_USER", "counselor"),
        "PASSWORD": os.environ.get("COURSE_IMPORT_DB_PASSWORD", ""),
        "HOST": host,
        "PORT": os.environ.get("COURSE_IMPORT_DB_PORT", "3306"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"charset": "utf8mb4"},
    }


DATABASES = {"default": importer_database()}
