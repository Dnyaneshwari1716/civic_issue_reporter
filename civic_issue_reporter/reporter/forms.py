# from django import forms
# from django.contrib.auth.forms import UserCreationForm
# from django.contrib.auth.models import User
# from .models import UserProfile

# class UserRegisterForm(UserCreationForm):
#     USER_TYPE_CHOICES = (
#         ('user', 'User'),
#         ('authority', 'Authority'),
#     )
#     user_type = forms.ChoiceField(choices=USER_TYPE_CHOICES)

#     class Meta:
#         model = User
#         fields = ['username', 'email', 'password1', 'password2', 'user_type']
