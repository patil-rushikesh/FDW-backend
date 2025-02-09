def send_email(receiver_email,subject,message):
    """Send OTP via email"""
    sender_email = os.getenv('EMAIL_ADDRESS')
    sender_password = os.getenv('EMAIL_PASSWORD')

    message = MIMEMultipart()
    message["From"] = sender_email
    message["To"] = receiver_email
    message["Subject"] = subject

    # Add logo
    logo_path = os.path.join(os.path.dirname(__file__), 'images', 'Teamaansh1.jpeg')
    
    with open(logo_path, 'rb') as logo_file:
        logo = MIMEImage(logo_file.read())
        logo.add_header('Content-ID', '<logo>')
        message.attach(logo)
    

    body = f"""
    <html>
    <body>
    <p>Dear User,</p>
    <p>We're excited to have you on board with <b>Team AANSH</b>.</p>
    {message}
    <p>Sincerely,<br>
    Team AANSH</p>
    <p><img src="cid:logo" alt="Team AANSH" style="width:100%;heigh:100px;align:center"></p>
    </body>
    </html>
    """

    message.attach(MIMEText(body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.send_message(message)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False
    
def send_username_password_mail(receiver_email,username,password):
    """Send username and password via email"""
    subject = "Team AANSH - Account Credentials"
    message = f"""
    <p>Your account credentials are as follows:</p>
    <p>Username: <b>{username}</b></p>
    <p>Password: <b>{password}</b></p>
    <p>Use these credentials to login to your account.</p>
    """
    return send_email(receiver_email, subject, message)


