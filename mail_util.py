import smtplib
import yaml
from email.message import EmailMessage
from log_util import Logging
from config_reader import SmtpConfig

# Enclose the mail sending logic in a function
def send_email(subject, body, config: SmtpConfig, logger: Logging):

    # Create the plain-text email
    message = EmailMessage()
    message.set_content(body)  # Set email body
    message['Subject'] = subject  # Set email subject
    message['From'] = config.login  # Set email from

    # Send the email to all recipients
    message['To'] = config.recipients#['smtp']['recipients']  # Set current recipient
    # Send the email
    try:
        # Create an SMTP object and specify the server and the port
        with smtplib.SMTP(config.server, config.port) as server:
            server.starttls()  # Start TLS encryption
            server.login(config.login, config.password)  # Log in to the SMTP server
            server.send_message(message)  # Send the email
            logger.log(f"Email sent successfully to {config.recipients}!")
    except Exception as e:
        logger.error(f"Error sending email to {config.recipients}: {e}")

def mail(message: str, config: SmtpConfig, logger: Logging):
    logger.log(message)
    if config is not None:
        send_email("ZFS-Autobackup with UDEV Trigger", message, config, logger)
    
def mail_error(message: str, config: SmtpConfig, logger: Logging):
    logger.error(message)
    if config is not None:
        send_email("ERROR: ZFS-Autobackup with UDEV Trigger", message, config, logger)

def mail_exception(message: str, config: SmtpConfig, logger: Logging):
    logger.exception(message)
    if config is not None:
        send_email("ERROR: ZFS-Autobackup with UDEV Trigger", message, config, logger)