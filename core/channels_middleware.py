# core/channels_middleware.py
import logging
from urllib.parse import parse_qs
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from core.cognito_auth import get_verifier

logger = logging.getLogger(__name__)
User = get_user_model()


@database_sync_to_async
def get_user_from_token(token):
    try:
        verifier = get_verifier()
        claims = verifier.verify_access_token(token)
        sub = claims.get('sub')
        if sub:
            user, _ = User.objects.get_or_create(id=sub)
            return user
    except Exception as e:
        logger.warning("WebSocket token verification failed: %s", type(e).__name__)
    return AnonymousUser()


class CognitoTokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        query_string = scope.get('query_string', b'').decode()
        params = parse_qs(query_string)
        token = params.get('token', [None])[0]

        if token:
            scope['user'] = await get_user_from_token(token)
        else:
            logger.debug("WebSocket /chat/ connection has no query param 'token'")
            scope['user'] = AnonymousUser()

        return await super().__call__(scope, receive, send)