"""
ASGI config for core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

from django.core.asgi import get_asgi_application

# Load Django first - must happen before importing channels_middleware/routing
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from core.channels_middleware import CognitoTokenAuthMiddleware
import chat.routing as routing

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': CognitoTokenAuthMiddleware(
        URLRouter(
            routing.websocket_urlpatterns
        )
    )
})
