import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time

# Generic email sender function
def send_email(subject, message_body):
    
    """Send email alerts for device status changes."""
    smtp_config = load_smtp_config("smtp-config.json")
    if not smtp_config:
        print("Failed to load SMTP configuration")
        return

    # Retrieve admin email addresses
    try:
        db_connected = dbConnect()
        if not db_connected:
            print("Failed to connect to database for fetching admin emails")
            return

        cursor = db_connected.cursor()

        # Query to get email addresses of admin users
        query = "SELECT email FROM adminuser"
        cursor.execute(query)
        email_results = cursor.fetchall()
        to_email = [row[0] for row in email_results]

    except Exception as e:
        print(f"Error while fetching admin emails: {e}")
        return

    finally:
        if cursor:
            cursor.close()
        if db_connected and db_connected.is_connected():
            db_connected.close()
    
    try:
        # Create a multipart email message
        msg = MIMEText(message_body)
        msg['From'] = smtp_config['sender_email']
        msg['To'] = ", ".join(to_email)
        msg['Subject'] = subject

        try:
            # Send the email
            with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['port']) as server:
                server.starttls()
                server.login(smtp_config['sender_email'], smtp_config['sender_password'])
                server.sendmail(smtp_config['sender_email'], to_email, msg.as_string()) # Send email

        print(f"Email sent successfully to {to_email} with subject: {subject}")
        return True

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# Function for handling email notifications
def email_notification_handler(ip_results=None, temperature=None):
    """
    Handles email notifications based on ip_results or temperature.

    Parameters:
        ip_results (list of tuples): List of devices that went offline, with (hostname, ip_address).
        temperature (float): Current temperature value to check if > 35°C.
    """
    # Notify about offline devices
    if ip_results and ip_results is not None:
        subject = "Device(s) Status Changed: Offline"
        message_body = "The following device(s) is offline:"
        for hostname, ip_address in ip_results:
            message_body += f"\n\nHostname: {hostname}\nIP Address: {ip_address}\n\nPlease take immediate action."    
        
        send_email(subject, message_body)

    # Notify about high temperature
    if temperature is not None and temperature > 35:
        subject = "Temperature Alert: High Temperature Detected"
        message_body = f"Warning: The recorded temperature is {temperature}°C, which exceeds the threshold of 35°C.\n\nPlease investigate the issue immediately."
        send_email(subject, message_body)