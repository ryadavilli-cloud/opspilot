"""Reviewer identity — who approved a report, proven rather than asserted (Stage 5e, G-01).

The HITL gate is v1's publication control, and a control that anyone can satisfy controls nothing.
Before this module, `InvestigationDecision.approver` was a client-supplied string: `curl -d
'{"approver": "someone"}'` produced an approval record indistinguishable from real human review.
Here the approver is *derived from a validated Entra token* and the client cannot influence it.

**Why not the app's managed identity.** Managed identity answers "which workload is calling Azure?"
— it is how this app reaches Azure OpenAI and Cosmos. It has no human behind it, so signing an
approval with it would only re-create the auto-approve stub with better cryptography. Code
guidelines §15 states the rule directly: *reviewer identity is a human Entra identity, not a
workload identity.* `auth_method` keeps that distinction on the record: a token minted for a service
principal is accepted where one is configured (the deploy smoke gate needs to drive the path) but is
never labelled `human`.

**No bypass exists.** There is deliberately no "auth disabled" backend. Validation always runs, so
the code exercised by the test suite is the code that runs in production; only the signing key
differs. Tests mint their own RS256 keypair and serve it through the same JWKS seam Entra fills in
production (see `tests/test_auth.py`). An env-gated bypass would put an unauthenticated approval
path in the shipped image, guarded by nothing but a string comparison — precisely the fail-open
shape §21 prohibits.

**What is verified**, all of it fail-closed — any failure raises `ReviewerAuthError` and the
endpoint answers 401/403, never a default principal:
  - the signature, against the issuer's published JWKS (RS256; `alg` is pinned, so a token cannot
    downgrade itself to `none` or to a symmetric algorithm verified with a public key);
  - `iss` — exactly the configured tenant's issuer;
  - `aud` — this API's own audience, so a token minted for a *different* app in the same tenant
    cannot be replayed here;
  - `exp` / `nbf`, with a small leeway for clock skew;
  - the approver role: authentication proves *who*, authorization proves *allowed to publish*.
    Signing in to the tenant is not consent to publish a production RCA.

`subject` is the token's `oid` (immutable per user per tenant), never `preferred_username` or
`email`, which are display values and can be reassigned. The audit record binds the subject, not the
label shown next to it.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Literal, Protocol

import jwt
from jwt import PyJWKClient
from pydantic import BaseModel, Field

from opspilot import config

# How an identity was established. Only `entra_jwt` is a human; `service_principal` is a workload
# token accepted so the deployed smoke gate can drive the decision path, and it must never be
# reported as human review. `_AUTO_APPROVE` is the deterministic sync path's non-identity.
AuthMethod = Literal["entra_jwt", "service_principal", "deterministic_auto_approval"]

# Entra stamps app-only (client-credentials) tokens with this claim; a token obtained by a signed-in
# user does not carry `idtyp: app`. It is how a service principal is told apart from a human without
# trusting anything the caller chose.
_APP_TOKEN_CLAIM = "idtyp"
_APP_TOKEN_VALUE = "app"

# Clock-skew allowance on exp/nbf. Small deliberately: this is tolerance for drift between Azure and
# the container host, not a grace period for expired tokens.
_LEEWAY_SECONDS = 60


class ReviewerAuthError(Exception):
    """Authentication or authorization failed. Carries an HTTP status (401 vs 403 — unproven
    identity vs proven identity lacking the role) and a *client-safe* reason.

    The reason is deliberately coarse ("token signature is not valid", not "expected iss=X, got
    iss=Y"): a detailed failure reason at an unauthenticated endpoint is a probing oracle. The
    precise cause is logged server-side by the caller instead.
    """

    def __init__(self, reason: str, *, status_code: int = 401) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


class ReviewerPrincipal(BaseModel):
    """A verified human (or, explicitly, a non-human) decision-maker. Frozen: nothing downstream of
    validation may edit an identity into something it was not proven to be."""

    model_config = {"frozen": True}

    # The immutable Entra object id (`oid`) — the thing the audit trail binds to. Not the username:
    # display names and emails are reassignable, so a record keyed on one can silently change who it
    # appears to name.
    subject: str
    tenant_id: str
    # Human-readable label for display only. Never used for identity comparisons or authorization.
    display_name: str
    roles: tuple[str, ...] = Field(default_factory=tuple)
    auth_method: AuthMethod

    @property
    def is_human(self) -> bool:
        """Whether this principal represents an actual person. Drives the approval record's `kind`,
        which must never be inferred from a string comparison against a sentinel approver name."""
        return self.auth_method == "entra_jwt"

    def audit_label(self) -> str:
        """The stable string written to the approval record: method-qualified so a reader can never
        mistake a service-principal decision for a human one, and subject-keyed so it stays
        unambiguous when two people share a display name."""
        return f"{self.auth_method}:{self.subject}"


class ReviewerAuthenticator(Protocol):
    """The seam. `api.py` depends on this, never on a concrete validator, so tests can supply a
    principal directly without the endpoint knowing the difference."""

    def authenticate(self, authorization_header: str | None) -> ReviewerPrincipal: ...


def _bearer_token(authorization_header: str | None) -> str:
    """Extract the bearer token, rejecting anything malformed before it reaches the JWT library."""
    if not authorization_header:
        raise ReviewerAuthError("an Authorization header is required")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ReviewerAuthError("Authorization must be a Bearer token")
    return token.strip()


class EntraJwtAuthenticator:
    """Validates a Microsoft Entra ID access token and maps it to a `ReviewerPrincipal`.

    `signing_key_resolver` is the JWKS seam: production passes Entra's published key set (fetched
    and cached by `PyJWKClient`), tests pass their own. It exists so validation logic is never
    branched on environment — the same verification runs everywhere, over a different key.
    """

    def __init__(
        self,
        *,
        issuer: str,
        audience: str,
        approver_role: str,
        signing_key_resolver: Any,
    ) -> None:
        self._issuer = issuer
        self._audience = audience
        self._approver_role = approver_role
        self._keys = signing_key_resolver

    def authenticate(self, authorization_header: str | None) -> ReviewerPrincipal:
        token = _bearer_token(authorization_header)

        try:
            signing_key = self._keys.get_signing_key_from_jwt(token).key
        except Exception as exc:  # noqa: BLE001 — any resolver failure is an auth failure
            # Includes an unknown `kid`, a malformed token, and JWKS being unreachable. Failing
            # closed on an unreachable JWKS is deliberate: an approval must not be accepted because
            # the key service was down.
            raise ReviewerAuthError("token signing key could not be resolved") from exc

        try:
            claims = jwt.decode(
                token,
                signing_key,
                # Pinned, not read from the token's own header — otherwise a caller could present
                # `alg: none`, or an HS256 token signed with the *public* key it can trivially read.
                algorithms=["RS256"],
                issuer=self._issuer,
                audience=self._audience,
                leeway=_LEEWAY_SECONDS,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise ReviewerAuthError("token has expired") from exc
        except jwt.InvalidTokenError as exc:
            # Covers a bad signature, wrong issuer, wrong audience, not-yet-valid, missing claims.
            # Collapsed into one client-safe reason on purpose — see ReviewerAuthError.
            raise ReviewerAuthError("token is not valid for this API") from exc

        return self._principal_from(claims)

    def _principal_from(self, claims: dict[str, Any]) -> ReviewerPrincipal:
        # `oid` is the immutable per-tenant object id. Entra always issues it for both users and
        # service principals; `sub` is pairwise-scoped per application, so it is not stable across
        # the tenant and makes a poor audit key.
        subject = claims.get("oid") or claims.get("sub")
        if not subject:
            raise ReviewerAuthError("token carries no subject claim")

        roles = tuple(claims.get("roles") or ())
        if self._approver_role not in roles:
            # Authenticated, but not permitted — 403, and deliberately distinguished from 401 so a
            # legitimate reviewer missing a role assignment gets an actionable answer.
            raise ReviewerAuthError(
                f"principal lacks the {self._approver_role!r} role required to decide",
                status_code=403,
            )

        is_app = claims.get(_APP_TOKEN_CLAIM) == _APP_TOKEN_VALUE
        display = (
            claims.get("preferred_username")
            or claims.get("name")
            or claims.get("app_displayname")
            or str(subject)
        )
        return ReviewerPrincipal(
            subject=str(subject),
            tenant_id=str(claims.get("tid", "")),
            display_name=str(display),
            roles=roles,
            auth_method="service_principal" if is_app else "entra_jwt",
        )


class _CachedJwks:
    """Entra's published signing keys, fetched lazily and refreshed periodically.

    `PyJWKClient` already caches, but it is constructed here rather than at import so a JWKS
    endpoint that is slow or briefly unreachable degrades the first decision request instead of
    crash-looping the container at startup — the same reasoning that made the graph and repository
    lazy in `api.py`.
    """

    def __init__(self, jwks_uri: str, *, ttl_seconds: int = 3600) -> None:
        self._uri = jwks_uri
        self._ttl = ttl_seconds
        self._client: PyJWKClient | None = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def get_signing_key_from_jwt(self, token: str) -> Any:
        with self._lock:
            now = time.monotonic()
            if self._client is None or now - self._fetched_at > self._ttl:
                self._client = PyJWKClient(self._uri, cache_keys=True)
                self._fetched_at = now
            client = self._client
        return client.get_signing_key_from_jwt(token)


def build_reviewer_authenticator() -> ReviewerAuthenticator:
    """Build the authenticator from config. Every required setting is validated here so a
    misconfigured deployment fails at the first decision request with a clear error, rather than
    silently accepting tokens it should have rejected.

    There is no `none`/`insecure` backend by design — see the module docstring.
    """
    tenant = config.ENTRA_TENANT_ID
    audience = config.ENTRA_API_AUDIENCE
    role = config.ENTRA_APPROVER_ROLE

    missing = [
        name
        for name, value in (
            ("AZURE_TENANT_ID", tenant),
            ("OPSPILOT_API_AUDIENCE", audience),
            ("OPSPILOT_APPROVER_ROLE", role),
        )
        if not value
    ]
    if missing:
        raise ValueError(
            "reviewer authentication is not configured; missing: " + ", ".join(missing)
        )

    # v2.0 issuer/JWKS. Tokens minted by the v1 endpoint carry a different `iss`, so they will be
    # rejected here — intentional: one accepted issuer, not a permissive set.
    issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
    jwks_uri = f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"

    return EntraJwtAuthenticator(
        issuer=issuer,
        audience=audience,
        approver_role=role,
        signing_key_resolver=_CachedJwks(jwks_uri),
    )


__all__ = [
    "AuthMethod",
    "EntraJwtAuthenticator",
    "ReviewerAuthError",
    "ReviewerAuthenticator",
    "ReviewerPrincipal",
    "build_reviewer_authenticator",
]
