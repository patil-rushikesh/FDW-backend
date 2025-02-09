from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
import os
import smtplib

def send_email(receiver_email, subject, email_body):
    """Send an email with an HTML message and an image."""
    sender_email = os.getenv('EMAIL_ADDRESS')
    sender_password = os.getenv('EMAIL_PASSWORD')

    msg = MIMEMultipart("related")  # Use "related" to handle inline images properly
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = subject

    # HTML Email Body
    body = f"""
    <html>
    <body>    
    <p><img src="cid:logo" alt="Team AANSH" style="width:100%;height:30%;display:block;margin:auto;"></p>
    <p>Dear User,</p>
    <p>We're excited to have you on board with <b>Team AANSH</b>.</p>
    {email_body}
    <p>Sincerely,<br>
    Team AANSH</p>
    </body>
    </html>
    """

    msg.attach(MIMEText(body, "html"))  # Attach HTML body

    # Attach logo image
    logo_path = os.path.join(os.path.dirname(__file__), 'images', 'Teamaansh1.jpeg')
    
    try:
        with open(logo_path, 'rb') as logo_file:
            logo = MIMEImage(logo_file.read())
            logo.add_header('Content-ID', '<logo>')  # Inline image
            logo.add_header("Content-Disposition", "inline", filename="Teamaansh1.jpeg")
            msg.attach(logo)
    except Exception as e:
        print(f"Error attaching image: {e}")

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_username_password_mail(receiver_email, username, password):
    """Send username and password via email"""
    subject = "Team AANSH - Account Credentials"
    email_body = f"""
    <p>Your account credentials are as follows:</p>
    <p>Username: <b>{username}</b></p>
    <p>Password: <b>{password}</b></p>
    <p>Use these credentials to login to your account.</p>
    """
    return send_email(receiver_email, subject, email_body)
