"""
Cognito JWT Token Verification & DRF Authentication

This module:
  1. Fetches Cognito's JWKS (public keys) and caches them
  2. Verifies JWT access tokens (signature, expiry, issuer, token_use)
  3. Verifies JWT ID tokens (signature, expiry, issuer, audience, token_use)
  4. Provides a DRF authentication class that attaches the Django user to requests

The frontend sends tokens in ENCODED form — all decoding and
verification happens here on the backend.
"""

import json
import time
import logging
import urllib.request

import jwt
from jwt.algorithms import RSAAlgorithm

from django.conf import settings
from django.contrib.auth import get_user_model

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)

User = get_user_model()


# ──────────────────────────────────────────────
# Cognito Token Verifier (JWKS-based)
# ──────────────────────────────────────────────

class CognitoTokenVerifier:
    """
    Verifies Cognito JWT tokens using the User Pool's JWKS public keys.

    - Access tokens are verified with: issuer, exp, token_use=access
    - ID tokens are verified with: issuer, audience (client_id), exp, token_use=id

    JWKS keys are cached in-memory to avoid fetching on every request.
    """

    _jwks_cache = None
    _jwks_cache_time = 0
    _cache_duration = 3600  # Re-fetch JWKS every hour

    def __init__(self):
        self.region = settings.COGNITO_AWS_REGION
        self.user_pool_id = settings.COGNITO_USER_POOL_ID
        self.client_id = settings.COGNITO_APP_CLIENT_ID
        self.issuer = (
            f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
        )
        self.jwks_url = f"{self.issuer}/.well-known/jwks.json"

    # ── JWKS fetching / caching ──

    def _get_jwks(self):
        """Fetch JWKS from Cognito, using a time-based cache."""
        now = time.time()
        if (
            CognitoTokenVerifier._jwks_cache
            and (now - CognitoTokenVerifier._jwks_cache_time) < self._cache_duration
        ):
            return CognitoTokenVerifier._jwks_cache

        logger.info("Fetching JWKS from %s", self.jwks_url)
        response = urllib.request.urlopen(self.jwks_url)
        CognitoTokenVerifier._jwks_cache = json.loads(response.read())
        CognitoTokenVerifier._jwks_cache_time = now
        return CognitoTokenVerifier._jwks_cache

    def _get_public_key(self, token):
        """
        Extract the 'kid' from the JWT header and find the matching
        RSA public key in the JWKS.
        """
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        if not kid:
            raise AuthenticationFailed("Token header missing 'kid'")

        # Try cached keys first
        key = self._find_key(kid)
        if key:
            return key

        # Cache miss — force refresh and retry
        CognitoTokenVerifier._jwks_cache = None
        key = self._find_key(kid)
        if key:
            return key

        raise AuthenticationFailed(
            "Unable to find matching public key for token verification"
        )

    def _find_key(self, kid):
        """Search JWKS for a key matching the given kid."""
        jwks = self._get_jwks()
        for key_data in jwks.get("keys", []):
            if key_data.get("kid") == kid:
                return RSAAlgorithm.from_jwk(json.dumps(key_data))
        return None

    # ── Token verification ──

    def verify_access_token(self, token):
        """
        Verify a Cognito ACCESS token.

        Checks: RS256 signature, issuer, expiry, token_use == 'access'.
        Note: Cognito access tokens do NOT contain an 'aud' claim.
        """
        public_key = self._get_public_key(token)

        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={
                    "verify_aud": False,  # Access tokens have no 'aud'
                    "verify_exp": True,
                },
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("Access token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f"Invalid access token: {e}")

        if payload.get("token_use") != "access":
            raise AuthenticationFailed("Token is not an access token")

        return payload

    def verify_id_token(self, token):
        """
        Verify a Cognito ID token.

        Checks: RS256 signature, issuer, audience (client_id), expiry,
        token_use == 'id'.
        """
        public_key = self._get_public_key(token)

        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience=self.client_id,
                options={
                    "verify_exp": True,
                },
            )
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("ID token has expired")
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed(f"Invalid ID token: {e}")

        if payload.get("token_use") != "id":
            raise AuthenticationFailed("Token is not an ID token")

        return payload


# ── Singleton accessor ──

_verifier = None


def get_verifier():
    global _verifier
    if _verifier is None:
        _verifier = CognitoTokenVerifier()
    return _verifier


# ──────────────────────────────────────────────
# DRF Authentication Class
# ──────────────────────────────────────────────

class CognitoAuthentication(BaseAuthentication):
    """
    Django REST Framework authentication class.

    Reads the Authorization header:
        Authorization: Bearer <access_token>

    Verifies the access token against Cognito's JWKS, then finds or
    creates a Django User whose pk matches the Cognito 'sub' claim.
    """

    def authenticate(self, request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not auth_header.startswith("Bearer "):
            return None  # No Bearer token — let other auth backends try

        token = auth_header[7:]  # Strip 'Bearer '

        verifier = get_verifier()
        payload = verifier.verify_access_token(token)

        sub = payload.get("sub")
        if not sub:
            raise AuthenticationFailed("Token missing 'sub' claim")

        # Find or create the Django user keyed on Cognito sub (UUID)
        try:
            user = User.objects.get(id=sub)
        except User.DoesNotExist:
            # Create a minimal user — profile will be populated via /sync/
            user = User(id=sub)
            user.set_unusable_password()
            user.save()
            logger.info("Created new user from Cognito sub: %s", sub)

        return (user, payload)

    def authenticate_header(self, request):
        """Return the WWW-Authenticate header for 401 responses."""
        return "Bearer"
