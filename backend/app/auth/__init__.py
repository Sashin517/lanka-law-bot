"""Firebase authentication boundary for protected backend APIs."""

from app.auth.firebase_auth import (
    FirebaseConfigurationError,
    get_current_user_id,
    init_firebase_admin,
)

__all__ = [
    "FirebaseConfigurationError",
    "get_current_user_id",
    "init_firebase_admin",
]
