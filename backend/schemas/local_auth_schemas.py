"""Pydantic v2 schemas for LOCAL auth mode endpoints.

Password fields use SecretStr to prevent accidental serialisation to logs.
Password policy is NIST SP 800-63B aligned (min-length + denylist; no composition rules).
Email-match check (check_password_not_email) is a service-layer helper for when
the email is not available at schema-validation time.
"""

from pydantic import BaseModel, EmailStr, SecretStr, field_validator
from utils.config import Config


def _normalise_email_value(v: object) -> object:
    """Lowercase and strip an email value; non-strings pass through for EmailStr to validate."""
    return v.strip().lower() if isinstance(v, str) else v


# Top ~200 passwords from Have I Been Pwned / SecLists; normalised to lowercase.

_COMMON_PASSWORDS: frozenset[str] = frozenset({
    "password", "password1", "password123", "password1234", "password12345",
    "123456", "1234567", "12345678", "123456789", "1234567890",
    "111111", "11111111", "000000", "0000000000",
    "1q2w3e4r", "1q2w3e", "1q2w3e4r5t", "qwerty", "qwerty123", "qwertyuiop",
    "asdfghjkl", "zxcvbnm", "abcdefgh",
    "letmein", "welcome", "welcome1", "welcome123",
    "monkey", "monkey1", "dragon", "master", "sunshine", "princess",
    "shadow", "iloveyou", "trustno1", "superman", "batman",
    "football", "baseball", "soccer", "hockey", "basketball",
    "abc123", "abc1234", "abcd1234",
    "admin", "admin123", "administrator",
    "login", "login123", "passw0rd", "pass123", "pass1234",
    "test", "test123", "testing", "testing123",
    "hello", "hello123", "hello1234",
    "secret", "secret1", "secret123",
    "changeme", "change_me", "changeme123",
    "michael", "ashley", "jessica", "charlie", "andrew", "daniel",
    "joshua", "david", "james", "robert", "thomas",
    "nicole", "jessica", "hunter", "jennifer", "jordan",
    "111222333", "123123", "321321", "654321", "987654321",
    "!@#$%^&*", "qazwsx", "1qaz2wsx",
    "computer", "internet", "windows", "linux", "ubuntu",
    "samsung", "iphone", "android", "google", "amazon",
    "passpass", "passwordpassword",
    "mustang", "ferrari", "porsche",
    "lovely", "pretty", "beautiful", "gorgeous",
    "flower", "chocolate", "butterfly", "diamond",
    "yankees", "manchester", "chelsea", "arsenal", "liverpool",
    "madison", "jessica", "brandon", "taylor", "morgan",
    "summer", "winter", "spring", "autumn",
    "maggie", "bailey", "buster", "goldie",
    "pa$$w0rd", "p@ssword", "p@ssw0rd", "p@$$w0rd",
    "abc", "12345", "123", "1234", "54321",
    "1111", "11111", "111111111", "1111111111",
    "0987654321", "9876543210",
    "google123", "facebook", "twitter",
    "baseball1", "basketball1", "football1",
    "password2", "password01", "password11",
    "aaaaaa", "bbbbbb", "cccccc", "zzzzzzz",
    "qqqqqq", "pppppp",
    "abcabc", "123abc", "abc123abc",
    "matrix", "starwars", "pokemon", "minecraft",
    "naruto", "bleach", "dragon123",
    "love123", "love1234", "loveyou",
    "monkey123", "dragon123", "shadow123",
    "super123", "super1234",
    "blue123", "red123", "green123",
    "house123", "home123", "homepass",
    "work123", "office123",
    "sky123", "earth123",
    "user", "user123", "user1234", "users",
    "guest", "guest123",
    "root", "root123", "toor",
    "temp", "temp123", "temporary",
    "default", "demo", "demo123",
    "service", "support", "helpdesk",
    "netpass", "netword", "network",
    "company", "company1",
    "apple123", "orange123",
    "bear123", "tiger123", "lion123",
    "pass", "pass1", "pass12",
    "secure", "secure123", "security",
    "access", "access123",
    "system", "system123",
    "manager", "manager123",
    "account", "account123",
    "member", "member123",
    "developer", "develop",
    "michael1", "daniel1", "matthew1",
    "abcdefg", "aaaaaaaa",
    "mypassword", "mypass", "mypassword1",
    "newpassword", "newpass",
    "oldpassword", "oldpass",
    "wrongpassword",
    "passme", "passme123",
    "love", "loveme", "loveme123",
    "cats", "dogs", "birds",
    "fish", "horse", "rabbit",
    "minecraft1", "roblox", "fortnite",
    "gaming", "gamer", "gamer123",
    "hacker", "hacking",
})


_MIN_LENGTH: int = Config.get_int_env_var("LOCAL_PASSWORD_MIN_LENGTH", default=12)


def _validate_password_strength(plain: str) -> str:
    """Apply password policy; raises ValueError with a user-safe message on rejection."""
    if len(plain) < _MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {_MIN_LENGTH} characters long."
        )
    if len(plain.encode("utf-8")) > 72:
        raise ValueError("Password must be at most 72 bytes long.")
    if plain.lower() in _COMMON_PASSWORDS:
        raise ValueError(
            "This password is too common. Please choose a more unique password."
        )
    return plain


def check_password_not_email(plain: str, email: str) -> None:
    """Raise PasswordPolicyError (HTTP 400) when password matches the email local-part.

    Called explicitly from the service layer where the email is known; deferred import
    avoids a circular dependency (schemas -> services -> schemas).
    """
    from services.auth.credential_service import PasswordPolicyError  # noqa: PLC0415

    local_part = email.split("@")[0].lower()
    if local_part and plain.lower() == local_part:
        raise PasswordPolicyError(
            "Password must not match your email address."
        )


class SetPasswordRequest(BaseModel):
    """Request body for the set-password-via-token flow (first-time setup and admin resets)."""

    token: str
    new_password: SecretStr

    @field_validator("token", mode="before")
    @classmethod
    def _strip_token(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("new_password", mode="before")
    @classmethod
    def _validate_new_password(cls, v: object) -> object:
        plain = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        _validate_password_strength(plain)
        return v


class ChangePasswordRequest(BaseModel):
    """Request body for an authenticated user changing their own password."""

    current_password: SecretStr
    new_password: SecretStr

    @field_validator("new_password", mode="before")
    @classmethod
    def _validate_new_password(cls, v: object) -> object:
        plain = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        _validate_password_strength(plain)
        return v


class LoginRequest(BaseModel):
    """Request body for LOCAL auth email+password login."""

    email: EmailStr
    password: SecretStr

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, v: object) -> object:
        return _normalise_email_value(v)


class AdminCreateUserRequest(BaseModel):
    """Request body for an admin creating a LOCAL auth user. No password — admin issues a set-password token separately."""

    email: EmailStr
    name: str

    @field_validator("email", mode="before")
    @classmethod
    def _normalise_email(cls, v: object) -> object:
        return _normalise_email_value(v)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class AdminSetPasswordRequest(BaseModel):
    """Request body for an admin forcibly setting a user's password (emergency reset)."""

    new_password: SecretStr

    @field_validator("new_password", mode="before")
    @classmethod
    def _validate_new_password(cls, v: object) -> object:
        plain = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        _validate_password_strength(plain)
        return v
