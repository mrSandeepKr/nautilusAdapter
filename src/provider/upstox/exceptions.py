class AuthenticationError(Exception):
    """Base exception for all Upstox authentication-related issues."""


class TOTPGenerationError(AuthenticationError):
    """Raised when the TOTP code cannot be generated from the configured secret."""


class LoginCredentialsError(AuthenticationError):
    """Raised when Upstox rejects the username/password credentials."""


class TwoFactorAuthError(AuthenticationError):
    """Raised when the Upstox 2FA (TOTP) step fails."""


class RedirectChainError(AuthenticationError):
    """Raised when the OAuth redirect chain breaks or `code` cannot be resolved."""


class TokenExchangeError(AuthenticationError):
    """Raised when exchanging the authorization `code` for an access token fails."""


class MissingAuthenticationError(AuthenticationError):
    """Raised when an access token is missing or invalid when required."""