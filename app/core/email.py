import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

def generate_otp() -> str:
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(to_email: str, otp: str, purpose: str = "verification") -> bool:
    try:
        if purpose == "verification":
            subject = "Email Verification - Robina Matrimonial"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #1A5C35; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">Robina Matrimonial</h1>
                </div>
                <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1A5C35;">Email Verification</h2>
                    <p>Assalamu Alaikum,</p>
                    <p>Your verification code is:</p>
                    <div style="background: #1A5C35; color: white; font-size: 32px; 
                                font-weight: bold; text-align: center; padding: 20px; 
                                border-radius: 10px; letter-spacing: 8px; margin: 20px 0;">
                        {otp}
                    </div>
                    <p>This code expires in <strong>10 minutes</strong>.</p>
                    <p>If you did not request this, please ignore this email.</p>
                    <hr style="border: 1px solid #eee; margin: 20px 0;">
                    <p style="color: #888; font-size: 12px;">Robina Matrimonial — Find Your Perfect Match</p>
                </div>
            </body>
            </html>
            """
        else:
            subject = "Password Reset - Robina Matrimonial"
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #1A5C35; padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0;">Robina Matrimonial</h1>
                </div>
                <div style="background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #1A5C35;">Password Reset Request</h2>
                    <p>Assalamu Alaikum,</p>
                    <p>Your password reset code is:</p>
                    <div style="background: #1A5C35; color: white; font-size: 32px; 
                                font-weight: bold; text-align: center; padding: 20px; 
                                border-radius: 10px; letter-spacing: 8px; margin: 20px 0;">
                        {otp}
                    </div>
                    <p>This code expires in <strong>10 minutes</strong>.</p>
                    <p>If you did not request this, please ignore this email.</p>
                    <hr style="border: 1px solid #eee; margin: 20px 0;">
                    <p style="color: #888; font-size: 12px;">Robina Matrimonial — Find Your Perfect Match</p>
                </div>
            </body>
            </html>
            """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM}>"
        msg["To"] = to_email

        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(
                settings.MAIL_USERNAME,
                settings.MAIL_PASSWORD
            )
            server.sendmail(
                settings.MAIL_FROM,
                to_email,
                msg.as_string()
            )
        return True

    except Exception as e:
        print(f"Email error: {e}")
        return False