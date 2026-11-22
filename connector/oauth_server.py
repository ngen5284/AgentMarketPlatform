"""OAuth 2.1 provider used by the local Connector."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import html
import json
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qs, quote

from pydantic import AnyHttpUrl
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from mcp.server.auth.provider import (
    AccessToken, AuthorizationCode, AuthorizationParams, AuthorizeError,
    OAuthAuthorizationServerProvider, RefreshToken, TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

OAUTH_SCOPE = "mcp:tools"
OAUTH_SUPPORTED_SCOPES = {OAUTH_SCOPE, "offline_access"}
ACCESS_TTL = 3600
REFRESH_TTL = 30 * 24 * 60 * 60
CODE_TTL = 300
PBKDF2_ITERATIONS = 310_000


def create_password_hash(password: str) -> str:
    if not isinstance(password, str) or len(password) < 12:
        raise ValueError("OAuth 로그인 비밀번호는 12자 이상이어야 합니다.")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    enc = lambda value: base64.urlsafe_b64encode(value).decode("ascii")
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${enc(salt)}${enc(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        decode = lambda value: base64.urlsafe_b64decode(value.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), decode(salt), int(rounds))
        return secrets.compare_digest(actual, decode(expected))
    except (ValueError, TypeError, UnicodeError):
        return False


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class LocalOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    """Single-owner OAuth Authorization Server; token data persists in SQLite."""

    def __init__(self, database_path: Path, password_hash: str, issuer_url: str, resource_url: str):
        self.database_path = Path(database_path)
        self.password_hash = password_hash
        self.issuer_url = issuer_url
        self.issuer_base_url = issuer_url.rstrip("/")
        self.resource_url = resource_url.rstrip("/")
        self.pending: dict[str, dict] = {}
        self.failed_logins: dict[str, list[float]] = {}
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS clients(client_id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS codes(code_hash TEXT PRIMARY KEY, client_id TEXT NOT NULL, expires REAL NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tokens(token_hash TEXT PRIMARY KEY, kind TEXT NOT NULL, family TEXT NOT NULL, client_id TEXT NOT NULL, scopes TEXT NOT NULL, expires INTEGER NOT NULL, resource TEXT, subject TEXT);
                CREATE INDEX IF NOT EXISTS idx_tokens_family ON tokens(family);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        with self._db() as db:
            row = db.execute("SELECT data FROM clients WHERE client_id=?", (client_id,)).fetchone()
        return OAuthClientInformationFull.model_validate_json(row["data"]) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("OAuth client_id가 없습니다.")
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO clients VALUES (?, ?)", (client_info.client_id, client_info.model_dump_json()))

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        scopes = params.scopes or [OAUTH_SCOPE]
        if OAUTH_SCOPE not in scopes or any(scope not in OAUTH_SUPPORTED_SCOPES for scope in scopes):
            raise AuthorizeError(error="invalid_scope", error_description="지원하지 않는 권한 범위입니다.")
        if params.resource and params.resource.rstrip("/") != self.resource_url:
            raise AuthorizeError(error="invalid_target", error_description="MCP 리소스 주소가 일치하지 않습니다.")
        state = secrets.token_urlsafe(32)
        self.pending[state] = {"client_id": client.client_id, "params": params, "expires": time.time() + CODE_TTL}
        return f"{self.issuer_base_url}/oauth/login?state={quote(state)}"

    async def login_page(self, request: Request) -> Response:
        state = request.query_params.get("state", "")
        item = self.pending.get(state)
        if not item or item["expires"] < time.time():
            self.pending.pop(state, None)
            return HTMLResponse("<h2>인증 요청이 만료되었습니다. 외부 AI 연결을 다시 시도하세요.</h2>", status_code=400)
        return self._login_form(state)

    def _login_form(self, state: str, error: str = "", status: int = 200) -> HTMLResponse:
        state = html.escape(state, quote=True)
        message = f'<p style="color:#b42318">{html.escape(error)}</p>' if error else ""
        page = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connector OAuth 인증</title><style>body{{font:16px system-ui;max-width:420px;margin:8vh auto;padding:20px;color:#202124}}main{{border:1px solid #ddd;border-radius:12px;padding:24px}}input,button{{box-sizing:border-box;width:100%;padding:12px;margin-top:12px;font-size:16px}}button{{cursor:pointer}}</style>
<main><h2>Connector 인증</h2><p>외부 AI 서비스의 MCP 접근을 승인합니다.</p>{message}
<form method="post" action="/oauth/login/callback"><input type="hidden" name="state" value="{state}">
<label for="pw">OAuth 로그인 비밀번호</label><input id="pw" name="password" type="password" autocomplete="current-password" required autofocus>
<button type="submit">인증 및 연결 승인</button></form></main></html>"""
        return HTMLResponse(page, status_code=status)

    async def login_callback(self, request: Request) -> Response:
        form = parse_qs((await request.body()).decode("utf-8", errors="replace"))
        state, password = form.get("state", [""])[0], form.get("password", [""])[0]
        pending = self.pending.get(state)
        if not pending or pending["expires"] < time.time():
            self.pending.pop(state, None)
            return HTMLResponse("<h2>인증 요청이 만료되었습니다. 다시 연결하세요.</h2>", status_code=400)

        remote = request.client.host if request.client else "unknown"
        now = time.time()
        failures = [t for t in self.failed_logins.get(remote, []) if now - t < 300]
        self.failed_logins[remote] = failures
        if len(failures) >= 5:
            return self._login_form(state, "로그인 시도가 너무 많습니다. 5분 후 다시 시도하세요.", 429)
        if not self.password_hash or not verify_password(password, self.password_hash):
            failures.append(now)
            self.failed_logins[remote] = failures
            return self._login_form(state, "비밀번호가 올바르지 않습니다.", 401)

        params: AuthorizationParams = pending["params"]
        scopes = params.scopes or [OAUTH_SCOPE]
        resource = (params.resource or self.resource_url).rstrip("/")
        if OAUTH_SCOPE not in scopes or any(scope not in OAUTH_SUPPORTED_SCOPES for scope in scopes) or resource != self.resource_url:
            self.pending.pop(state, None)
            return HTMLResponse("<h2>요청한 권한 또는 MCP 주소가 유효하지 않습니다.</h2>", status_code=400)

        code = secrets.token_urlsafe(40)
        auth_code = AuthorizationCode(
            code=code, client_id=pending["client_id"], redirect_uri=AnyHttpUrl(str(params.redirect_uri)),
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            expires_at=time.time() + CODE_TTL, scopes=scopes, code_challenge=params.code_challenge,
            resource=self.resource_url, subject="connector-owner",
        )
        with self._db() as db:
            db.execute("INSERT INTO codes VALUES (?, ?, ?, ?)", (_digest(code), pending["client_id"], auth_code.expires_at, auth_code.model_dump_json()))
        self.pending.pop(state, None)
        destination = construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state, iss=self.issuer_url)
        return RedirectResponse(destination, status_code=302)

    async def load_authorization_code(self, client: OAuthClientInformationFull, authorization_code: str) -> AuthorizationCode | None:
        digest = _digest(authorization_code)
        with self._db() as db:
            row = db.execute("SELECT data, expires FROM codes WHERE code_hash=? AND client_id=?", (digest, client.client_id)).fetchone()
            if row and row["expires"] <= time.time():
                db.execute("DELETE FROM codes WHERE code_hash=?", (digest,))
                return None
        return AuthorizationCode.model_validate_json(row["data"]) if row else None

    async def exchange_authorization_code(self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode) -> OAuthToken:
        digest = _digest(authorization_code.code)
        with self._db() as db:
            row = db.execute("SELECT expires FROM codes WHERE code_hash=? AND client_id=?", (digest, client.client_id)).fetchone()
            if not row or row["expires"] <= time.time():
                raise TokenError(error="invalid_grant", error_description="인증 코드가 만료되었거나 이미 사용되었습니다.")
            db.execute("DELETE FROM codes WHERE code_hash=?", (digest,))
            return self._issue_pair(db, client.client_id, authorization_code.scopes, authorization_code.resource or self.resource_url, authorization_code.subject or "connector-owner")

    def _issue_pair(self, db, client_id: str, scopes: list[str], resource: str, subject: str) -> OAuthToken:
        now, family = int(time.time()), secrets.token_urlsafe(24)
        access, refresh = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
        scope_json = json.dumps(scopes)
        db.executemany("INSERT INTO tokens VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [
            (_digest(access), "access", family, client_id, scope_json, now + ACCESS_TTL, resource, subject),
            (_digest(refresh), "refresh", family, client_id, scope_json, now + REFRESH_TTL, resource, subject),
        ])
        return OAuthToken(access_token=access, token_type="Bearer", expires_in=ACCESS_TTL, scope=" ".join(scopes), refresh_token=refresh)

    async def load_access_token(self, token: str) -> AccessToken | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM tokens WHERE token_hash=? AND kind='access'", (_digest(token),)).fetchone()
            if row and row["expires"] <= int(time.time()):
                db.execute("DELETE FROM tokens WHERE family=?", (row["family"],))
                return None
        if not row:
            return None
        return AccessToken(token=token, client_id=row["client_id"], scopes=json.loads(row["scopes"]), expires_at=row["expires"], resource=row["resource"], subject=row["subject"], claims={"iss": self.issuer_url})

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        with self._db() as db:
            row = db.execute("SELECT * FROM tokens WHERE token_hash=? AND kind='refresh' AND client_id=?", (_digest(refresh_token), client.client_id)).fetchone()
            if row and row["expires"] <= int(time.time()):
                db.execute("DELETE FROM tokens WHERE family=?", (row["family"],))
                return None
        if not row:
            return None
        return RefreshToken(token=refresh_token, client_id=row["client_id"], scopes=json.loads(row["scopes"]), expires_at=row["expires"], resource=row["resource"], subject=row["subject"])

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]) -> OAuthToken:
        new_scopes = scopes or refresh_token.scopes
        if any(scope not in refresh_token.scopes for scope in new_scopes):
            raise TokenError(error="invalid_scope", error_description="기존 토큰에 없는 권한 범위입니다.")
        with self._db() as db:
            row = db.execute("SELECT family, expires FROM tokens WHERE token_hash=? AND kind='refresh' AND client_id=?", (_digest(refresh_token.token), client.client_id)).fetchone()
            if not row or row["expires"] <= int(time.time()):
                raise TokenError(error="invalid_grant", error_description="갱신 토큰이 만료되었거나 폐기되었습니다.")
            db.execute("DELETE FROM tokens WHERE family=?", (row["family"],))
            return self._issue_pair(db, client.client_id, new_scopes, refresh_token.resource or self.resource_url, refresh_token.subject or "connector-owner")

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        with self._db() as db:
            row = db.execute("SELECT family FROM tokens WHERE token_hash=?", (_digest(token.token),)).fetchone()
            if row:
                db.execute("DELETE FROM tokens WHERE family=?", (row["family"],))


class LocalTokenVerifier:
    """OAuth verifier plus compatibility for the two existing Connector tokens."""
    def __init__(self, provider: LocalOAuthProvider, resource_url: str, mcp_token: str, claude_token: str):
        self.provider, self.resource_url = provider, resource_url
        self.mcp_token, self.claude_token = mcp_token, claude_token

    async def verify_token(self, token: str) -> AccessToken | None:
        oauth_token = await self.provider.load_access_token(token)
        if oauth_token:
            return oauth_token
        if self.mcp_token and secrets.compare_digest(token, self.mcp_token):
            client_id = "connector-static-token"
        elif self.claude_token and secrets.compare_digest(token, self.claude_token):
            client_id = "connector-claude-test-token"
        else:
            return None
        return AccessToken(token=token, client_id=client_id, scopes=[OAUTH_SCOPE], resource=self.resource_url, subject="connector-owner")