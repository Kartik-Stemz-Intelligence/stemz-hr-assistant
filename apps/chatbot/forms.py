from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def _company_domain():
    return (settings.COMPANY_EMAIL_DOMAIN or '').strip().lower()


def _normalize_email(email):
    return (email or '').strip().lower()


class EmployeeLoginForm(forms.Form):
    email = forms.EmailField(
        label='Work email',
        widget=forms.EmailInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': 'strategy.intern03@stemzglobal.com',
            'autocomplete': 'email',
        }),
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': 'Your password',
            'autocomplete': 'current-password',
        }),
    )

    def clean_email(self):
        email = _normalize_email(self.cleaned_data['email'])
        company_domain = _company_domain()
        if company_domain and not email.endswith(f'@{company_domain}'):
            raise ValidationError(f'Use your @{company_domain} employee email.')
        return email


class EmployeeRegistrationRequestForm(forms.Form):
    full_name = forms.CharField(
        label='Full name',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': 'Your name',
            'autocomplete': 'name',
        }),
    )
    email = forms.EmailField(
        label='Work email',
        widget=forms.EmailInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': 'strategy.intern03@stemzglobal.com',
            'autocomplete': 'email',
        }),
    )

    def clean_email(self):
        email = _normalize_email(self.cleaned_data['email'])
        validate_email(email)

        company_domain = _company_domain()
        if company_domain and not email.endswith(f'@{company_domain}'):
            raise ValidationError(f'Only @{company_domain} employee emails can register.')

        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError('An account already exists for this email address.')
        return email


class EmployeeRegistrationVerifyForm(forms.Form):
    code = forms.CharField(
        label='Verification code',
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm tracking-[0.3em] text-center uppercase focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': '123456',
            'autocomplete': 'one-time-code',
            'inputmode': 'numeric',
        }),
    )

    def clean_code(self):
        code = (self.cleaned_data.get('code') or '').strip()
        if not code.isdigit():
            raise ValidationError('Enter the 6-digit code sent to your email.')
        return code


class EmployeeRegistrationPasswordForm(forms.Form):
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': 'Create a password',
            'autocomplete': 'new-password',
        }),
    )
    password2 = forms.CharField(
        label='Confirm password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'w-full rounded-xl border border-neutral-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand focus:border-brand',
            'placeholder': 'Repeat your password',
            'autocomplete': 'new-password',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError('Passwords do not match.')
        if password1:
            validate_password(password1)
        return cleaned_data