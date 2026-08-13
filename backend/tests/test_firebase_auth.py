from __future__ import annotations

import unittest
from pathlib import Path
from typing import Annotated
from unittest.mock import MagicMock, patch

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from firebase_admin import auth as firebase_auth
from pydantic import ValidationError

from app.auth import firebase_auth as auth_module
from app.auth.firebase_auth import (
    FirebaseConfigurationError,
    get_current_user_id,
    init_firebase_admin,
)
from app.core.config import Settings, settings


def _bearer(token: str = "firebase-id-token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class FirebaseAdminInitializationTests(unittest.TestCase):
    def test_existing_default_app_is_reused(self) -> None:
        existing_app = MagicMock(name="firebase_app")
        existing_app.project_id = "law-bot-production"
        with (
            patch.object(
                auth_module.firebase_admin, "get_app", return_value=existing_app
            ),
            patch.object(auth_module.firebase_admin, "initialize_app") as initialize,
        ):
            result = init_firebase_admin()

        self.assertIs(result, existing_app)
        initialize.assert_not_called()

    def test_service_account_initialization_uses_explicit_project(self) -> None:
        initialized_app = MagicMock(name="firebase_app")
        initialized_app.project_id = "law-bot-production"
        credential = MagicMock(name="credential")
        resolved_path = Path("C:/secure/firebase-service-account.json")

        with (
            patch.object(
                auth_module.firebase_admin,
                "get_app",
                side_effect=ValueError("default app missing"),
            ),
            patch.object(
                auth_module.firebase_admin,
                "initialize_app",
                return_value=initialized_app,
            ) as initialize,
            patch.object(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", "credential.json"),
            patch.object(settings, "FIREBASE_PROJECT_ID", "law-bot-production"),
            patch.object(Path, "resolve", return_value=resolved_path),
            patch.object(Path, "is_file", return_value=True),
            patch.object(
                auth_module.credentials, "Certificate", return_value=credential
            ) as certificate,
        ):
            result = init_firebase_admin()

        self.assertIs(result, initialized_app)
        certificate.assert_called_once_with(str(resolved_path))
        initialize.assert_called_once_with(
            credential,
            options={"projectId": "law-bot-production"},
        )

    def test_adc_initialization_allows_credential_derived_project(self) -> None:
        initialized_app = MagicMock(name="firebase_app")
        initialized_app.project_id = "law-bot-adc"
        with (
            patch.object(
                auth_module.firebase_admin,
                "get_app",
                side_effect=ValueError("default app missing"),
            ),
            patch.object(
                auth_module.firebase_admin,
                "initialize_app",
                return_value=initialized_app,
            ) as initialize,
            patch.object(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", ""),
            patch.object(settings, "FIREBASE_PROJECT_ID", ""),
        ):
            result = init_firebase_admin()

        self.assertIs(result, initialized_app)
        initialize.assert_called_once_with(options=None)

    def test_missing_project_identity_discards_new_app_and_fails_fast(self) -> None:
        initialized_app = MagicMock(name="firebase_app")
        initialized_app.project_id = None
        with (
            patch.object(
                auth_module.firebase_admin,
                "get_app",
                side_effect=ValueError("default app missing"),
            ),
            patch.object(
                auth_module.firebase_admin,
                "initialize_app",
                return_value=initialized_app,
            ),
            patch.object(auth_module.firebase_admin, "delete_app") as delete_app,
            patch.object(settings, "FIREBASE_SERVICE_ACCOUNT_PATH", ""),
            patch.object(settings, "FIREBASE_PROJECT_ID", ""),
            self.assertRaisesRegex(
                FirebaseConfigurationError,
                "project identity could not be resolved",
            ),
        ):
            init_firebase_admin()

        delete_app.assert_called_once_with(initialized_app)

    def test_missing_service_account_file_fails_without_initializing(self) -> None:
        with (
            patch.object(
                auth_module.firebase_admin,
                "get_app",
                side_effect=ValueError("default app missing"),
            ),
            patch.object(auth_module.firebase_admin, "initialize_app") as initialize,
            patch.object(
                settings,
                "FIREBASE_SERVICE_ACCOUNT_PATH",
                "missing-firebase-service-account.json",
            ),
            patch.object(Path, "is_file", return_value=False),
            self.assertRaisesRegex(
                FirebaseConfigurationError,
                "service-account file was not found",
            ),
        ):
            init_firebase_admin()

        initialize.assert_not_called()

    def test_credential_parse_failure_is_wrapped_without_leaking_details(self) -> None:
        with (
            patch.object(
                auth_module.firebase_admin,
                "get_app",
                side_effect=ValueError("default app missing"),
            ),
            patch.object(
                settings,
                "FIREBASE_SERVICE_ACCOUNT_PATH",
                "firebase-service-account.json",
            ),
            patch.object(Path, "is_file", return_value=True),
            patch.object(
                auth_module.credentials,
                "Certificate",
                side_effect=ValueError("private credential parsing detail"),
            ),
            self.assertRaisesRegex(
                FirebaseConfigurationError,
                "Firebase Admin initialization failed",
            ) as raised,
        ):
            init_firebase_admin()

        self.assertNotIn("private credential", str(raised.exception))


class FirebaseTokenDependencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_or_non_bearer_credentials_fail_closed(self) -> None:
        for authorization in (
            None,
            HTTPAuthorizationCredentials(scheme="Basic", credentials="token"),
        ):
            with self.subTest(authorization=authorization):
                with self.assertRaises(HTTPException) as raised:
                    await get_current_user_id(authorization)  # type: ignore[arg-type]

                self.assertEqual(raised.exception.status_code, 401)
                self.assertEqual(
                    raised.exception.headers,
                    {"WWW-Authenticate": "Bearer"},
                )

    async def test_valid_token_returns_normalized_uid_with_security_options(
        self,
    ) -> None:
        firebase_app = MagicMock(name="firebase_app")
        with (
            patch.object(auth_module, "init_firebase_admin", return_value=firebase_app),
            patch.object(
                auth_module.firebase_auth,
                "verify_id_token",
                return_value={
                    "uid": "  firebase-user-1  ",
                    "email": "user@example.com",
                },
            ) as verify,
            patch.object(settings, "FIREBASE_CHECK_REVOKED_TOKENS", True),
            patch.object(
                settings,
                "FIREBASE_SERVICE_ACCOUNT_PATH",
                "firebase-service-account.json",
            ),
            patch.object(settings, "FIREBASE_CLOCK_SKEW_SECONDS", 15),
        ):
            user_id = await get_current_user_id(_bearer())

        self.assertEqual(user_id, "firebase-user-1")
        verify.assert_called_once_with(
            "firebase-id-token",
            app=firebase_app,
            check_revoked=True,
            clock_skew_seconds=15,
        )

    async def test_expired_token_returns_specific_401(self) -> None:
        error = firebase_auth.ExpiredIdTokenError("expired", ValueError("cause"))
        raised = await self._verification_error(error)

        self.assertEqual(raised.status_code, 401)
        self.assertEqual(raised.detail, "Authentication token expired.")
        self.assertEqual(raised.headers, {"WWW-Authenticate": "Bearer"})

    async def test_invalid_revoked_and_disabled_tokens_return_generic_401(self) -> None:
        errors = (
            firebase_auth.InvalidIdTokenError("invalid"),
            firebase_auth.RevokedIdTokenError("revoked"),
            firebase_auth.UserDisabledError("disabled"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                raised = await self._verification_error(error)
                self.assertEqual(raised.status_code, 401)
                self.assertEqual(raised.detail, "Invalid authentication token.")

    async def test_certificate_and_unexpected_failures_return_503(self) -> None:
        errors = (
            firebase_auth.CertificateFetchError(
                "certificate fetch failed", RuntimeError("network")
            ),
            RuntimeError("unexpected verifier failure"),
        )
        for error in errors:
            with self.subTest(error=type(error).__name__):
                raised = await self._verification_error(error)
                self.assertEqual(raised.status_code, 503)
                self.assertEqual(
                    raised.detail,
                    "Authentication service is unavailable.",
                )
                self.assertIsNone(raised.headers)

    async def test_unexpected_failure_returns_generic_503_to_clients(self) -> None:
        sensitive_message = "must-not-appear-token-material"
        with self.assertLogs(auth_module.logger.name, level="ERROR") as captured:
            raised = await self._verification_error(RuntimeError(sensitive_message))

        self.assertEqual(raised.status_code, 503)
        self.assertEqual(raised.detail, "Authentication service is unavailable.")
        self.assertNotIn(sensitive_message, raised.detail)
        self.assertIn("Unexpected Firebase token verification failure", "\n".join(captured.output))

    async def test_initialization_failure_returns_503_without_verification(
        self,
    ) -> None:
        with (
            patch.object(
                auth_module,
                "init_firebase_admin",
                side_effect=FirebaseConfigurationError("bad configuration"),
            ),
            patch.object(auth_module.firebase_auth, "verify_id_token") as verify,
            self.assertRaises(HTTPException) as raised,
        ):
            await get_current_user_id(_bearer())

        self.assertEqual(raised.exception.status_code, 503)
        verify.assert_not_called()

    async def test_missing_oversized_or_invalid_uid_is_rejected(self) -> None:
        cases: tuple[dict[str, object], ...] = (
            {},
            {"uid": "   "},
            {"uid": "x" * 129},
            {"uid": 123},
        )
        for decoded in cases:
            with self.subTest(decoded=decoded):
                with (
                    patch.object(
                        auth_module,
                        "init_firebase_admin",
                        return_value=MagicMock(name="firebase_app"),
                    ),
                    patch.object(
                        auth_module.firebase_auth,
                        "verify_id_token",
                        return_value=decoded,
                    ),
                    self.assertRaises(HTTPException) as raised,
                ):
                    await get_current_user_id(_bearer())

                self.assertEqual(raised.exception.status_code, 401)

        with (
            patch.object(auth_module, "init_firebase_admin") as initialize,
            self.assertRaises(HTTPException) as oversized,
        ):
            await get_current_user_id(_bearer("x" * 16_385))
        self.assertEqual(oversized.exception.status_code, 401)
        initialize.assert_not_called()

    async def _verification_error(self, error: Exception) -> HTTPException:
        with (
            patch.object(
                auth_module,
                "init_firebase_admin",
                return_value=MagicMock(name="firebase_app"),
            ),
            patch.object(
                auth_module.firebase_auth,
                "verify_id_token",
                side_effect=error,
            ),
            self.assertRaises(HTTPException) as raised,
        ):
            await get_current_user_id(_bearer())
        return raised.exception


class FirebaseConfigurationTests(unittest.TestCase):
    def test_clock_skew_is_restricted_to_firebase_supported_range(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, FIREBASE_CLOCK_SKEW_SECONDS=61)

        configured = Settings(
            _env_file=None,
            FIREBASE_CLOCK_SKEW_SECONDS=60,
            FIREBASE_CHECK_REVOKED_TOKENS=False,
        )
        self.assertEqual(configured.FIREBASE_CLOCK_SKEW_SECONDS, 60)
        self.assertFalse(configured.FIREBASE_CHECK_REVOKED_TOKENS)


class FirebaseHttpIntegrationTests(unittest.TestCase):
    def test_http_bearer_token_flows_through_dependency(self) -> None:
        app = FastAPI()

        @app.get("/protected")
        async def protected_endpoint(
            user_id: Annotated[str, Depends(get_current_user_id)],
        ) -> dict[str, str]:
            return {"user_id": user_id}

        with (
            patch.object(
                auth_module,
                "init_firebase_admin",
                return_value=MagicMock(name="firebase_app"),
            ),
            patch.object(
                auth_module.firebase_auth,
                "verify_id_token",
                return_value={"uid": "firebase-user-http"},
            ) as verify,
            TestClient(app) as client,
        ):
            missing = client.get("/protected")
            authenticated = client.get(
                "/protected",
                headers={"Authorization": "Bearer real-client-token"},
            )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(
            authenticated.json(),
            {"user_id": "firebase-user-http"},
        )
        verify.assert_called_once()
        self.assertEqual(verify.call_args.args[0], "real-client-token")
