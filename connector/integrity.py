import hashlib
import json
from pathlib import Path


EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc"}
INTEGRITY_FILE = "integrity.json"


def _included_files(package_dir: Path):
    package_dir = package_dir.resolve()
    files = []

    for path in package_dir.rglob("*"):
        if not path.is_file():
            continue

        relative = path.relative_to(package_dir)

        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue

        if path.suffix.lower() in EXCLUDED_SUFFIXES:
            continue

        if relative.as_posix() == INTEGRITY_FILE:
            continue

        if path.is_symlink():
            raise ValueError(f"심볼릭 링크 파일은 허용되지 않습니다: {relative}")

        files.append(path)

    return sorted(files, key=lambda item: item.relative_to(package_dir).as_posix())


def _calculate_sha256(file_path: Path) -> str:
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def create_integrity_manifest(package_dir: str | Path) -> dict:
    package_dir = Path(package_dir).resolve()

    if not package_dir.is_dir():
        raise ValueError("패키지 폴더가 존재하지 않습니다.")

    files = {}

    for path in _included_files(package_dir):
        relative = path.relative_to(package_dir).as_posix()
        files[relative] = _calculate_sha256(path)

    integrity = {
        "algorithm": "sha256",
        "files": files,
    }

    integrity_path = package_dir / INTEGRITY_FILE

    integrity_path.write_text(
        json.dumps(integrity, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return integrity


def verify_package_integrity(package_dir: str | Path) -> dict:
    package_dir = Path(package_dir).resolve()
    integrity_path = package_dir / INTEGRITY_FILE

    if not integrity_path.is_file():
        return {
            "success": False,
            "message": "integrity.json이 없습니다.",
            "missing": [],
            "modified": [],
            "unexpected": [],
        }

    try:
        integrity = json.loads(integrity_path.read_text(encoding="utf-8"))

        if not isinstance(integrity, dict):
            raise ValueError("무결성 정보 형식이 올바르지 않습니다.")

        if integrity.get("algorithm") != "sha256":
            raise ValueError("지원하지 않는 해시 알고리즘입니다.")

        expected = integrity.get("files")

        if not isinstance(expected, dict) or not expected:
            raise ValueError("무결성 파일 목록이 비어 있거나 올바르지 않습니다.")

        for name, digest in expected.items():
            if (
                not isinstance(name, str)
                or not isinstance(digest, str)
                or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("잘못된 파일 해시 정보가 있습니다.")

    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {
            "success": False,
            "message": f"무결성 정보 읽기 실패: {exc}",
            "missing": [],
            "modified": [],
            "unexpected": [],
        }

    actual_files = {
        path.relative_to(package_dir).as_posix(): path
        for path in _included_files(package_dir)
    }

    expected_names = set(expected)
    actual_names = set(actual_files)

    missing = sorted(expected_names - actual_names)
    unexpected = sorted(actual_names - expected_names)

    modified = []

    for name in sorted(expected_names & actual_names):
        actual_hash = _calculate_sha256(actual_files[name])

        if actual_hash != expected[name]:
            modified.append(name)

    success = not missing and not modified and not unexpected

    return {
        "success": success,
        "message": "패키지 무결성 검증 성공" if success else "패키지 무결성 검증 실패",
        "missing": missing,
        "modified": modified,
        "unexpected": unexpected,
    }
