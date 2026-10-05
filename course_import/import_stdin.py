"""Import one converted course from stdin. Used inside the local Docker web container.

The container environment already points at the local MySQL service. This script
refuses any host other than that local service.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["COURSE_IMPORT_DB_HOST"] = os.environ.get("DB_HOST", "db")
os.environ["COURSE_IMPORT_DB_NAME"] = os.environ.get("DB_NAME", "")
os.environ["COURSE_IMPORT_DB_USER"] = os.environ.get("DB_USER", "")
os.environ["COURSE_IMPORT_DB_PASSWORD"] = os.environ.get("DB_PASSWORD", "")
os.environ["COURSE_IMPORT_DB_PORT"] = os.environ.get("DB_PORT", "3306")

from course_import.dbimport import CourseImportError, run_import


def main():
    request = json.load(sys.stdin)
    db = {
        "host": os.environ["COURSE_IMPORT_DB_HOST"],
        "port": os.environ["COURSE_IMPORT_DB_PORT"],
        "name": os.environ["COURSE_IMPORT_DB_NAME"],
        "user": os.environ["COURSE_IMPORT_DB_USER"],
        "password": os.environ["COURSE_IMPORT_DB_PASSWORD"],
    }
    try:
        summary = run_import(
            request.get("payload") or {},
            request.get("config") or {},
            db,
            dry_run=bool(request.get("dry_run")),
        )
    except CourseImportError as exc:
        sys.stderr.write(str(exc))
        raise SystemExit(1)
    sys.stdout.write(json.dumps(summary))


if __name__ == "__main__":
    main()
