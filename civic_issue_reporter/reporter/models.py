
'''
# Create your models here.
from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    USER_TYPE_CHOICES = (
        ('user', 'User'),
        ('authority', 'Authority'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)

    def __str__(self):
        return f"{self.user.username} ({self.user_type})"

class Complaint(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    issue_type = models.CharField(max_length=255)
    description = models.TextField()
    location = models.CharField(max_length=255)
    image = models.ImageField(upload_to='complaints/')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Complaint by {self.user.username} - {self.issue_type}"
'''
from django.db import models
from accounts.models import CustomUser

class Department(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField()
    jurisdiction = models.CharField(max_length=100)
    issue_types = models.TextField(help_text="Comma-separated issue types")
    
    def __str__(self):
        return self.name

class Complaint(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Resolved', 'Resolved')
    ]
    
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True)
    image = models.ImageField(upload_to='complaints/')
    issue_type = models.CharField(max_length=100)
    description = models.TextField()
    location = models.CharField(max_length=255)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)
    resolution_notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.issue_type} at {self.location}"