"""Reviewer identity (G-01) — proves the decision endpoint's approval gate cannot be satisfied by
an unauthenticated, forged, or unauthorized caller.

**These tests drive the real production validator.** There is no auth-bypass backend to test
around: `EntraJwtAuthenticator` is the same class the deployed app runs, and the only substitution
is the JWKS seam, which is handed a keypair generated here instead of Entra's published one. That
is the point — a bypass-based test suite exercises the bypass, not the thing that ships.

Azure-free and network-free: the keypair is generated in-process and the "JWKS" is a local object,
so this runs in the CI gate lane like everything else.
"""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from opspilot.auth import EntraJwtAuthenticator, ReviewerAuthError

ISSUER = "https://login.microsoftonline.com/test-tenant-id/v2.0"
AUDIENCE = "api://opspilot-test"
ROLE = "Approver"
OTHER_KEY_ID = "attacker-key"


@pytest.fixture(scope="module")
def keypair():
    """One RSA keypair for the module — generation is the slow part; every test signs with it."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def rogue_keypair():
    """A second, untrusted keypair — stands in for an attacker signing their own tokens."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _StaticJwks:
    """The JWKS seam: returns the one key we trust, exactly as `PyJWKClient` would in production.
    Raises for any other `kid`, which is how an unknown signing key fails closed."""

    def __init__(self, private_key, kid: str = "test-key") -> None:
        self._public = private_key.public_key()
        self._kid = kid

    def get_signing_key_from_jwt(self, token: str):
        header = jwt.get_unverified_header(token)
        if header.get("kid") != self._kid:
            raise LookupError(f"unknown kid {header.get('kid')!r}")
        return type("Key", (), {"key": self._public})()


def _authenticator(private_key) -> EntraJwtAuthenticator:
    return EntraJwtAuthenticator(
        issuer=ISSUER,
        audience=AUDIENCE,
        approver_role=ROLE,
        signing_key_resolver=_StaticJwks(private_key),
    )


def _token(private_key, *, kid: str = "test-key", **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "pairwise-subject",
        "oid": "11111111-2222-3333-4444-555555555555",
        "tid": "test-tenant-id",
        "preferred_username": "reviewer@example.com",
        "roles": [ROLE],
        "iat": now,
        "nbf": now - 10,
        "exp": now + 600,
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


def _header(token: str) -> str:
    return f"Bearer {token}"


# --------------------------------------------------------------------------------------
# The happy path, and what it is allowed to assert
# --------------------------------------------------------------------------------------
def test_a_valid_token_yields_a_human_principal(keypair):
    principal = _authenticator(keypair).authenticate(_header(_token(keypair)))

    assert principal.is_human
    assert principal.auth_method == "entra_jwt"
    # Identity binds to the immutable object id, NOT the reassignable username.
    assert principal.subject == "11111111-2222-3333-4444-555555555555"
    assert principal.audit_label() == "entra_jwt:11111111-2222-3333-4444-555555555555"
    assert principal.display_name == "reviewer@example.com"


def test_subject_prefers_oid_over_the_pairwise_sub(keypair):
    # `sub` is scoped per-application, so it is not a stable tenant-wide audit key. If `oid` is
    # present it must win — otherwise the same person records differently across apps.
    principal = _authenticator(keypair).authenticate(_header(_token(keypair)))
    assert principal.subject != "pairwise-subject"


def test_an_app_token_is_accepted_but_never_labelled_human(keypair):
    # The deploy smoke gate authenticates as a service principal. It must be able to drive the
    # decision path, and it must NOT be reportable as human review (code guidelines §15).
    token = _token(keypair, idtyp="app", app_displayname="opspilot-smoke")
    principal = _authenticator(keypair).authenticate(_header(token))

    assert principal.auth_method == "service_principal"
    assert not principal.is_human
    assert principal.audit_label().startswith("service_principal:")


# --------------------------------------------------------------------------------------
# Forgery and replay
# --------------------------------------------------------------------------------------
def test_a_token_signed_by_an_untrusted_key_is_rejected(keypair, rogue_keypair):
    # The core forgery case: well-formed, correct claims, wrong signer.
    forged = _token(rogue_keypair, kid=OTHER_KEY_ID)
    with pytest.raises(ReviewerAuthError) as exc:
        _authenticator(keypair).authenticate(_header(forged))
    assert exc.value.status_code == 401


def test_a_tampered_payload_is_rejected(keypair):
    # Flip a claim after signing: the signature no longer matches the body.
    token = _token(keypair)
    head, payload, sig = token.split(".")
    tampered = f"{head}.{payload[:-4]}AAAA.{sig}"
    with pytest.raises(ReviewerAuthError):
        _authenticator(keypair).authenticate(_header(tampered))


def test_an_alg_none_token_is_rejected(keypair):
    # `algorithms` is pinned to RS256, so a caller cannot strip the signature by declaring `none`.
    unsigned = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "sub": "x"}, key="", algorithm="none")
    with pytest.raises(ReviewerAuthError):
        _authenticator(keypair).authenticate(_header(unsigned))


def test_a_token_for_another_audience_is_rejected(keypair):
    # Replay defence: a token legitimately minted for a different app in the SAME tenant is signed
    # by the same Entra keys and would otherwise validate.
    token = _token(keypair, aud="api://some-other-app")
    with pytest.raises(ReviewerAuthError):
        _authenticator(keypair).authenticate(_header(token))


def test_a_token_from_another_issuer_is_rejected(keypair):
    token = _token(keypair, iss="https://login.microsoftonline.com/other-tenant/v2.0")
    with pytest.raises(ReviewerAuthError):
        _authenticator(keypair).authenticate(_header(token))


def test_an_expired_token_is_rejected(keypair):
    now = int(time.time())
    token = _token(keypair, exp=now - 3600, nbf=now - 7200, iat=now - 7200)
    with pytest.raises(ReviewerAuthError) as exc:
        _authenticator(keypair).authenticate(_header(token))
    assert exc.value.status_code == 401


def test_a_not_yet_valid_token_is_rejected(keypair):
    now = int(time.time())
    token = _token(keypair, nbf=now + 3600, exp=now + 7200)
    with pytest.raises(ReviewerAuthError):
        _authenticator(keypair).authenticate(_header(token))


def test_an_unknown_signing_key_fails_closed(keypair):
    # Unresolvable `kid` — also the shape of a JWKS outage. An approval must not be accepted
    # because the key service could not answer.
    with pytest.raises(ReviewerAuthError):
        _authenticator(keypair).authenticate(_header(_token(keypair, kid="never-published")))


# --------------------------------------------------------------------------------------
# Authorization is separate from authentication
# --------------------------------------------------------------------------------------
def test_an_authenticated_principal_without_the_role_gets_403(keypair):
    # Signed in to the tenant is not consent to publish a production RCA.
    token = _token(keypair, roles=["Reader"])
    with pytest.raises(ReviewerAuthError) as exc:
        _authenticator(keypair).authenticate(_header(token))
    assert exc.value.status_code == 403


def test_a_token_with_no_roles_claim_at_all_gets_403(keypair):
    token = _token(keypair, roles=[])
    with pytest.raises(ReviewerAuthError) as exc:
        _authenticator(keypair).authenticate(_header(token))
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------------------
# Malformed headers never reach the JWT library
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "header",
    [None, "", "token-without-scheme", "Basic dXNlcjpwYXNz", "Bearer", "Bearer    "],
)
def test_malformed_authorization_headers_are_rejected(keypair, header):
    with pytest.raises(ReviewerAuthError) as exc:
        _authenticator(keypair).authenticate(header)
    assert exc.value.status_code == 401


def test_the_scheme_match_is_case_insensitive(keypair):
    # RFC 7235 makes the scheme case-insensitive; rejecting "bearer" would be a real-client bug.
    principal = _authenticator(keypair).authenticate(f"bearer {_token(keypair)}")
    assert principal.is_human


# --------------------------------------------------------------------------------------
# Configuration fails loud rather than defaulting to something weaker
# --------------------------------------------------------------------------------------
def test_the_factory_refuses_to_build_when_unconfigured(monkeypatch):
    from opspilot import auth, config

    monkeypatch.setattr(config, "ENTRA_TENANT_ID", "")
    monkeypatch.setattr(config, "ENTRA_API_AUDIENCE", "")
    monkeypatch.setattr(config, "ENTRA_APPROVER_ROLE", "Approver")

    with pytest.raises(ValueError, match="AZURE_TENANT_ID"):
        auth.build_reviewer_authenticator()


def test_there_is_no_backend_that_disables_authentication():
    """A structural guard, not a behavioural one: the moment someone adds an `insecure`/`none`
    authenticator 'just for local dev', this fails. That path is what G-01 was."""
    import inspect

    from opspilot import auth

    source = inspect.getsource(auth)
    for forbidden in ("class InsecureAuth", "class NoopAuth", "auth_method=\"none\""):
        assert forbidden not in source
