"""Firebase Admin initialization and FastAPI bearer-token verification."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Annotated, Any

import firebase_admin
from fastapi import Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from firebase_admin import exceptions as firebase_exceptions

from app.core.config import settings

logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(auto_error=False)
_initialization_lock = Lock()
_MAX_ID_TOKEN_LENGTH = 16_384
_MAX_FIREBASE_UID_LENGTH = 128


class FirebaseConfigurationError(RuntimeError):
    """Raised when Firebase Admin cannot be initialized safely."""


def init_firebase_admin() -> firebase_admin.App:
    """Return the default Firebase app, initializing it once per process.

    The double-checked lock protects test runners and multi-threaded startup
    paths from attempting to create the default app concurrently.
    """
    existing = _get_default_app()
    if existing is not None:
        return _require_project_identity(existing)

    with _initialization_lock:
        existing = _get_default_app()
        if existing is not None:
            return _require_project_identity(existing)
        return _initialize_default_app()


async def get_current_user_id(
    authorization: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer_scheme),
    ],
) -> str:
    """Verify a Firebase ID token and return its non-empty UID claim."""
    if authorization is None or authorization.scheme.lower() != "bearer":
        raise _unauthorized("Missing authentication token.")

    id_token = authorization.credentials.strip()
    if not id_token:
        raise _unauthorized("Missing authentication token.")
    if len(id_token) > _MAX_ID_TOKEN_LENGTH:
        raise _unauthorized("Invalid authentication token.")

    try:
        app = init_firebase_admin()
    except FirebaseConfigurationError as exc:
        logger.error("Firebase authentication is not configured: %s", exc)
        raise _authentication_unavailable() from exc

    should_check_revoked = settings.FIREBASE_CHECK_REVOKED_TOKENS and bool(
        settings.FIREBASE_SERVICE_ACCOUNT_PATH.strip()
        or settings.FIREBASE_SERVICE_ACCOUNT_JSON.strip()
    )
    try:
        decoded = await run_in_threadpool(
            firebase_auth.verify_id_token,
            id_token,
            app=app,
            check_revoked=should_check_revoked,
            clock_skew_seconds=settings.FIREBASE_CLOCK_SKEW_SECONDS,
        )
    except firebase_auth.ExpiredIdTokenError as exc:
        raise _unauthorized("Authentication token expired.") from exc
    except (firebase_auth.RevokedIdTokenError, firebase_auth.UserDisabledError) as exc:
        raise _unauthorized("Invalid authentication token.") from exc
    except firebase_auth.InvalidIdTokenError as exc:
        raise _unauthorized("Invalid authentication token.") from exc
    except firebase_auth.CertificateFetchError as exc:
        logger.warning(
            "Firebase public-key retrieval failed: %s - %s", type(exc).__name__, exc
        )
        raise _authentication_unavailable() from exc
    except firebase_exceptions.FirebaseError as exc:
        logger.warning(
            "Firebase token verification service failed: %s - %s",
            type(exc).__name__,
            exc,
        )
        raise _authentication_unavailable() from exc
    except Exception as exc:
        logger.error(
            "Unexpected Firebase token verification failure: %s - %s",
            type(exc).__name__,
            exc,
        )
        raise _authentication_unavailable() from exc

    user_id = decoded.get("uid") if isinstance(decoded, Mapping) else None
    if not isinstance(user_id, str):
        raise _unauthorized("Authentication token is missing a user identifier.")
    user_id = user_id.strip()
    if not user_id or len(user_id) > _MAX_FIREBASE_UID_LENGTH:
        raise _unauthorized("Authentication token is missing a user identifier.")
    return user_id


def _get_default_app() -> firebase_admin.App | None:
    try:
        return firebase_admin.get_app()
    except ValueError:
        return None


def _initialize_default_app() -> firebase_admin.App:
    service_account_path = settings.FIREBASE_SERVICE_ACCOUNT_PATH.strip()
    service_account_json = settings.FIREBASE_SERVICE_ACCOUNT_JSON.strip()
    project_id = settings.FIREBASE_PROJECT_ID.strip()
    options = {"projectId": project_id} if project_id else None

    app: firebase_admin.App | None = None
    try:
        if service_account_json:
            try:
                service_account_info = json.loads(service_account_json)
            except json.JSONDecodeError as exc:
                raise FirebaseConfigurationError(
                    "Configured Firebase service-account JSON is invalid."
                ) from exc
            if not isinstance(service_account_info, dict):
                raise FirebaseConfigurationError(
                    "Configured Firebase service-account JSON must be an object."
                )
            credential = credentials.Certificate(service_account_info)
            app = firebase_admin.initialize_app(credential, options=options)
            _require_project_identity(app)
            logger.info("Firebase Admin initialized from an environment secret.")
            return app

        if service_account_path:
            path = Path(service_account_path).expanduser().resolve()
            if not path.is_file():
                raise FirebaseConfigurationError(
                    "Configured Firebase service-account file was not found."
                )
            credential: Any = credentials.Certificate(str(path))
            app = firebase_admin.initialize_app(credential, options=options)
            _require_project_identity(app)
            logger.info("Firebase Admin initialized with a service account.")
            return app

        app = firebase_admin.initialize_app(options=options)
        _require_project_identity(app)
        logger.info("Firebase Admin initialized with application default credentials.")
        return app
    except FirebaseConfigurationError:
        _discard_new_app(app)
        raise
    except Exception as exc:
        _discard_new_app(app)
        raise FirebaseConfigurationError(
            "Firebase Admin initialization failed."
        ) from exc


def _require_project_identity(app: firebase_admin.App) -> firebase_admin.App:
    try:
        project_id = app.project_id
    except Exception as exc:
        raise FirebaseConfigurationError(
            "Firebase project identity could not be resolved."
        ) from exc
    if not isinstance(project_id, str) or not project_id.strip():
        raise FirebaseConfigurationError(
            "Firebase project identity could not be resolved."
        )
    return app


def _discard_new_app(app: firebase_admin.App | None) -> None:
    if app is None:
        return
    try:
        firebase_admin.delete_app(app)
    except ValueError as exc:
        logger.warning("Failed to discard invalid Firebase app: %s", type(exc).__name__)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _authentication_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Authentication service is unavailable.",
    )
