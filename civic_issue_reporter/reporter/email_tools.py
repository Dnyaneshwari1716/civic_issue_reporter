# reporter/email_tools.py
'''
import smtplib
from email.message import EmailMessage
from typing import Optional
from django.conf import settings

def send_email_to_authority(
    receiver_email: str,
    sender_name: str,
    subject: str,
    body: str,
) -> str:
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{settings.EMAIL_HOST_USER}>"
        msg["To"] = receiver_email
        msg.set_content(body)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            smtp.send_message(msg)

        return "email sent successfully"
    except Exception as e:
        return f"error: {e}"
    '''

from django.conf import settings
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import smtplib
import os

def send_complaint_email(complaint):
    try:
        msg = MIMEMultipart()
        msg['Subject'] = f"New Complaint: {complaint.issue_type} at {complaint.location}"
        msg['From'] = f"Civic Reporter <{settings.EMAIL_HOST_USER}>"
        msg['To'] = complaint.department.email
        
        # Email body
        body = f"""
        Complaint Details:
        -----------------
        Type: {complaint.issue_type}
        Location: {complaint.location}
        Reported On: {complaint.created_at.strftime('%Y-%m-%d %H:%M')}
        
        Description:
        {complaint.description}
        
        Status: {complaint.status}
        """
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach image
        image_path = os.path.join(settings.MEDIA_ROOT, complaint.image.name)
        with open(image_path, 'rb') as f:
            img = MIMEImage(f.read())
            img.add_header('Content-Disposition', 'attachment', 
                         filename=os.path.basename(image_path))
            msg.attach(img)
        
        # Send email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            server.send_message(msg)
        
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False