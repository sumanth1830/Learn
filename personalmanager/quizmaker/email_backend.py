import os
import resend
from django.core.mail.backends.base import BaseEmailBackend


class ResendEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        resend.api_key = os.environ["RESEND_API_KEY"]
        sent_count = 0
        for message in email_messages:
            html_body = message.body
            if hasattr(message, "alternatives"):
                for content, mimetype in message.alternatives:
                    if mimetype == "text/html":
                        html_body = content
            try:
                resend.Emails.send({
                    "from": message.from_email,
                    "to": message.to,
                    "subject": message.subject,
                    "html": html_body,
                    "text": message.body,
                })
                sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent_count