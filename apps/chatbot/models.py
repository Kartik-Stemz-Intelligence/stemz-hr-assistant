from django.db import models


class Conversation(models.Model):
    session_key = models.CharField(max_length=64, db_index=True)
    user_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    title = models.CharField(max_length=120, blank=True)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'chatbot'
        ordering = ['-updated_at']

    def __str__(self):
        return self.title or f'Conversation #{self.pk}'

    @property
    def display_title(self):
        return self.title or f'Conversation #{self.pk}'


class Message(models.Model):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name='messages'
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.TextField()
    citation = models.CharField(max_length=255, blank=True)
    top_score = models.FloatField(null=True, blank=True)
    retrieved_titles = models.JSONField(default=list, blank=True)
    # Full source metadata (doc_title, version, approved_by, effective_date,
    # signed_on, section, excerpt, ...). Powers the click-to-verify UI on
    # historical messages so a reloaded conversation is as trustworthy as a
    # live one. Optional — pre-frontmatter messages have this empty.
    source = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'chatbot'
        ordering = ['created_at']

    def __str__(self):
        return f'{self.role}: {self.content[:60]}'


class AskHRRequest(models.Model):
    """A user's escalation from the chat — sent to HR by email, also stored
    here so nothing is lost if email delivery fails.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    conversation = models.ForeignKey(
        Conversation, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='ask_hr_requests',
    )
    user_name = models.CharField(max_length=120)
    user_email = models.EmailField()
    question = models.TextField(help_text="The user's last question in the chat")
    bot_answer = models.TextField(blank=True, help_text="What the bot said (if anything)")
    user_note = models.TextField(blank=True, help_text="Optional extra context from the user")
    transcript = models.JSONField(default=list, blank=True)
    retrieved_titles = models.JSONField(default=list, blank=True)
    top_score = models.FloatField(null=True, blank=True)
    email_status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    email_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = 'chatbot'
        ordering = ['-created_at']

    def __str__(self):
        return f'AskHR #{self.pk} from {self.user_name}'
