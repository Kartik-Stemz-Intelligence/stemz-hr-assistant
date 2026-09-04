import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.test import Client


def _company_email(local_part='strategy.intern03'):
    domain = (settings.COMPANY_EMAIL_DOMAIN or 'stemzglobal.com').strip().lower()
    return f'{local_part}@{domain}'


@pytest.mark.django_db
def test_chat_page_requires_login():
    client = Client()

    response = client.get(reverse('chat_page'))

    assert response.status_code == 302
    assert reverse('login') in response.url


@pytest.mark.django_db
def test_register_company_email_sends_verification_code(monkeypatch):
    client = Client()
    email = _company_email('new.employee.auth')
    User.objects.filter(username=email).delete()
    outbox = {}

    def fake_send_mail(subject, message, from_email, recipient_list, fail_silently=False):
        outbox['subject'] = subject
        outbox['message'] = message
        outbox['recipient_list'] = recipient_list
        return 1

    monkeypatch.setattr('apps.chatbot.views.send_mail', fake_send_mail)

    response = client.post(reverse('register'), {
        'full_name': 'Strategy Intern',
        'email': email,
    })

    assert response.status_code == 302
    assert response.url == reverse('register_verify')
    assert outbox['recipient_list'] == [email]
    session = client.session
    pending = session.get('employee_registration_pending')
    assert pending is not None
    assert pending['email'] == email
    assert pending['code_hash']


@pytest.mark.django_db
def test_register_rejects_non_company_email():
    client = Client()

    response = client.post(reverse('register'), {
        'full_name': 'Outside User',
        'email': 'someone@example.com',
    })

    assert response.status_code == 200
    assert b'Only @stemzglobal.com employee emails can register.' in response.content
    assert not User.objects.filter(username='someone@example.com').exists()


@pytest.mark.django_db
def test_register_verify_and_set_password_activates_user(monkeypatch):
    client = Client()
    email = _company_email('verify.employee.auth')
    User.objects.filter(username=email).delete()
    outbox = {}

    def fake_send_mail(subject, message, from_email, recipient_list, fail_silently=False):
        outbox['message'] = message
        return 1

    monkeypatch.setattr('apps.chatbot.views.send_mail', fake_send_mail)

    response = client.post(reverse('register'), {
        'full_name': 'Strategy Intern',
        'email': email,
    })
    assert response.status_code == 302
    assert response.url == reverse('register_verify')

    code_line = [line for line in outbox['message'].splitlines() if line.startswith('Code:')][0]
    code = code_line.split(':', 1)[1].strip()

    response = client.post(reverse('register_verify'), {
        'action': 'verify',
        'code': code,
    })
    assert response.status_code == 302
    assert response.url == reverse('register_password')

    response = client.post(reverse('register_password'), {
        'password1': 'StrongPass123!',
        'password2': 'StrongPass123!',
    })
    assert response.status_code == 302
    assert response.url == reverse('chat_page')

    user = User.objects.get(username=email)
    assert user.check_password('StrongPass123!')
    assert client.get(reverse('chat_page')).status_code == 200


@pytest.mark.django_db
def test_conversations_list_rejects_anonymous_api_calls():
    client = Client()

    response = client.get(reverse('conversations_list'))

    assert response.status_code == 401
    assert response.json()['error'] == 'Please log in with your employee account.'