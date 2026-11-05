import ast
from pathlib import Path


BLOCKED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "os.system",
    "os.popen",
    "subprocess.run",
    "subprocess.Popen",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.getoutput",
    "subprocess.getstatusoutput",
    "pty.spawn",
    "ctypes.CDLL",
    "ctypes.PyDLL",
    "ctypes.WinDLL",
    "ctypes.OleDLL",
    "pickle.load",
    "pickle.loads",
    "marshal.loads",
}

WARNING_CALLS = {
    "importlib.import_module",
    "yaml.load",
}

WARNING_MODULES = {
    "subprocess",
    "ctypes",
    "pickle",
    "marshal",
    "pty",
}

EXCLUDED_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
}

MAX_SOURCE_SIZE = 2 * 1024 * 1024


def _get_call_name(node):
    """Convert an AST call target into a dotted name."""

    parts = []

    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value

    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))

    return None


def _scan_python_file(file_path: Path, package_dir: Path) -> list[dict]:
    """Inspect Python source without executing it."""

    findings = []

    if file_path.is_symlink():
        return [{
            "severity": "block",
            "file": str(file_path.relative_to(package_dir)),
            "line": 0,
            "reason": "Python 소스 파일이 심볼릭 링크입니다.",
        }]

    resolved_path = file_path.resolve()

    if not resolved_path.is_relative_to(package_dir):
        return [{
            "severity": "block",
            "file": str(file_path),
            "line": 0,
            "reason": "패키지 외부를 가리키는 Python 파일입니다.",
        }]

    relative_path = str(file_path.relative_to(package_dir))

    try:
        if file_path.stat().st_size > MAX_SOURCE_SIZE:
            raise ValueError("Python 소스 파일이 허용 크기(2MB)를 초과합니다.")

        source = file_path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source, filename=relative_path)

    except (OSError, UnicodeError, SyntaxError, ValueError) as exc:
        return [{
            "severity": "block",
            "file": relative_path,
            "line": 0,
            "reason": f"Python 소스 분석 실패: {exc}",
        }]

    module_aliases = {}
    function_aliases = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_aliases[alias.asname or alias.name.split(".")[0]] = (
                    alias.name
                )

                if alias.name in WARNING_MODULES:
                    findings.append({
                        "severity": "warning",
                        "file": relative_path,
                        "line": node.lineno,
                        "reason": f"위험 가능성이 있는 모듈 import: {alias.name}",
                    })

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""

            for alias in node.names:
                if module:
                    function_aliases[alias.asname or alias.name] = (
                        f"{module}.{alias.name}"
                    )

            if module in WARNING_MODULES:
                findings.append({
                    "severity": "warning",
                    "file": relative_path,
                    "line": node.lineno,
                    "reason": f"위험 가능성이 있는 모듈 import: {module}",
                })

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        call_name = _get_call_name(node.func)

        if not call_name:
            continue

        first_part = call_name.split(".")[0]

        if first_part in module_aliases:
            call_name = module_aliases[first_part] + call_name[len(first_part):]

        elif call_name in function_aliases:
            call_name = function_aliases[call_name]

        if call_name in BLOCKED_CALLS:
            findings.append({
                "severity": "block",
                "file": relative_path,
                "line": node.lineno,
                "reason": f"위험한 코드 실행 호출: {call_name}",
            })

        elif call_name in WARNING_CALLS:
            findings.append({
                "severity": "warning",
                "file": relative_path,
                "line": node.lineno,
                "reason": f"추가 검토가 필요한 호출: {call_name}",
            })

    return findings


def verify_package_security(package_dir: str | Path) -> dict:
    """Statically inspect Python files in an agent package."""

    package_dir = Path(package_dir).resolve()

    if not package_dir.is_dir():
        return {
            "success": False,
            "message": "패키지 폴더가 존재하지 않습니다.",
            "blocked": True,
            "findings": [],
        }

    findings = []
    python_files = []

    for path in package_dir.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(package_dir).parts):
            continue

        python_files.append(path)

    if not python_files:
        findings.append({
            "severity": "block",
            "file": "",
            "line": 0,
            "reason": "검사할 Python 소스 파일이 없습니다.",
        })

    for file_path in sorted(python_files):
        findings.extend(_scan_python_file(file_path, package_dir))

    blocked = any(item["severity"] == "block" for item in findings)

    return {
        "success": not blocked,
        "message": (
            "패키지 보안 검사 통과"
            if not blocked
            else "위험한 코드 또는 검사 오류가 발견됐습니다."
        ),
        "blocked": blocked,
        "findings": findings,
    }
