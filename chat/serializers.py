from rest_framework import serializers
from .models import User, Profile, Connection, Message


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['thumbnail']


class SearchSerializer(serializers.ModelSerializer):
    """Serializer for search results — lightweight user info."""
    thumbnail = serializers.ImageField(source='profile.thumbnail', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['username', 'full_name', 'thumbnail', 'status']
    
    def get_status(self, obj):
        if obj.pending_them:
            return 'pending-them'
        if obj.pending_me:
            return 'pending-me'
        if obj.connected:
            return 'connected'
        return 'no-connection'


class UserSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for returning user profile data.
    Includes the nested profile (thumbnail).
    """
    thumbnail = serializers.ImageField(source='profile.thumbnail', read_only=True)

    class Meta:
        model = User
        fields = [
            'username',
            'full_name',
            'email',
            'phone_number',
            'kyc_status',
            'thumbnail',
        ]
        read_only_fields = ['username', 'kyc_status']

class RequestSerializer(serializers.ModelSerializer):
    sender = UserSerializer()
    reciever = UserSerializer()

    class Meta:
        model = Connection
        fields = [
            'sender',
            'reciever',
            'created'
        ]

class FriendSerializer(serializers.ModelSerializer):
    friend = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()
    updated = serializers.SerializerMethodField()

    class Meta:
        model = Connection
        fields = [
            'id',
            'friend',
            'preview',
            'updated'
        ]

    def get_friend(self, obj):
        #if im the sender
        if self.context['user'] == obj.sender:
            return UserSerializer(obj.reciever).data
        #if im the reciever
        elif self.context['user'] == obj.reciever:
            return UserSerializer(obj.sender).data
        else:
            print('Error: no user found in friendserializer')

    def get_preview(self, obj):
        default = 'New connection'
        if not hasattr(obj, 'latest_text'):
            return default
        return obj.latest_text or default

    def get_updated(self, obj):
        if not hasattr(obj, 'latest_created'):
            date = obj.updated
        else:
             date = obj.latest_created or obj.updated
        return date.isoformat()

class MessageSerializer(serializers.ModelSerializer):
    is_me = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id',
            'is_me',
            'text',
            'created'
        ]

    def get_is_me(self, obj):
        return obj.user == self.context['user']