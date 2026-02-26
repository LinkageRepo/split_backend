from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
import uuid


def upload_thumbnail(instance, filename):
    path = f'thumbnails/{instance.user.id}'
    extension = filename.split('.')[-1]
    if extension:
        path = path + '.' + extension
    return path

"""
class CustomUserManager(BaseUserManager):
    #Custom manager because USERNAME_FIELD is phone_number, not username.

    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('Phone number is required')
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone_number, password, **extra_fields)
"""

class User(AbstractUser):
    # Override AbstractUser's username with our own definition
    # Populated from the Cognito 'cognito:username' claim via /sync/
    username = models.CharField(max_length=150, unique=True, null=True, blank=True)

    # Primary key comes from the Cognito 'sub' attribute (UUID)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # User profile fields — populated from the Cognito ID token via /sync/
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    full_name = models.CharField(max_length=255, blank=True, default='')

    # KYC Status
    KYC_CHOICES = [
        ('PENDING', 'Pending'),
        ('VERIFIED', 'Verified'),
        ('REJECTED', 'Rejected'),
    ]
    kyc_status = models.CharField(max_length=10, choices=KYC_CHOICES, default='PENDING')

    #objects = CustomUserManager()

    # phone_number is the login identifier for Django admin / createsuperuser
    USERNAME_FIELD = 'phone_number'
    REQUIRED_FIELDS = ['full_name']

    def __str__(self):
        display = self.full_name or self.email or str(self.id)
        return f"{display} ({self.phone_number or 'no phone'})"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    thumbnail = models.ImageField(upload_to=upload_thumbnail, blank=True, null=True)

    def __str__(self):
        return f"Profile of {self.user}"

class Connection(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_connections')
    reciever = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_connections')
    accepted = models.BooleanField(default=False)
    updated = models.DateTimeField(auto_now=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.sender.username + ' -> ' + self.reciever.username

class Message(models.Model):
    connection = models.ForeignKey(Connection, on_delete=models.CASCADE, related_name='messages')
    user = models.ForeignKey(User, related_name='my_messages', on_delete=models.CASCADE)
    text = models.TextField()
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username + ':' + self.text