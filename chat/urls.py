from django.urls import path
from .views import TokenSyncView, UserProfileView

urlpatterns = [
    # POST — sync user profile from Cognito ID token after login
    path('sync/', TokenSyncView.as_view()),

    # GET — return authenticated user's profile
    path('me/', UserProfileView.as_view()),
]
