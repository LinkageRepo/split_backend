from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from core.cognito_auth import get_verifier, AuthenticationFailed
from .serializers import UserSerializer
from .models import Profile


class TokenSyncView(APIView):
    """
    POST /chat/sync/

    Called by the frontend right after Cognito login.
    The access token is verified automatically by CognitoAuthentication
    (via the Authorization header). This view additionally receives the
    raw ID token in the request body, verifies it, and creates / updates
    the Django user record with claims from the ID token.

    Request body (JSON):
        { "id_token": "<encoded JWT>" }

    Response:
        User profile JSON
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        id_token = request.data.get('id_token')
        if not id_token:
            return Response(
                {'error': 'id_token is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the ID token (signature, expiry, audience, issuer)
        verifier = get_verifier()
        try:
            claims = verifier.verify_id_token(id_token)
        except AuthenticationFailed as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Ensure the ID token belongs to the same user as the access token
        if str(request.user.id) != claims.get('sub'):
            return Response(
                {'error': 'ID token sub does not match authenticated user'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Update user profile from ID token claims
        user = request.user
        user.username = claims.get('cognito:username', None) or user.username
        user.email = claims.get('email', '') or user.email
        user.phone_number = claims.get('phone_number', None) or user.phone_number
        user.full_name = (
            claims.get('name', '')
            or ' '.join(
                filter(None, [claims.get('given_name', ''), claims.get('family_name', '')])
            )
            or user.full_name
        )
        user.save()

        # Ensure the user has a Profile (for thumbnail etc.)
        Profile.objects.get_or_create(user=user)

        return Response(UserSerializer(user).data)


class UserProfileView(APIView):
    """
    GET /chat/me/

    Returns the authenticated user's profile.
    Access token is verified automatically by CognitoAuthentication.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
