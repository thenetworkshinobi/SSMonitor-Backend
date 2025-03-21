import mysql.connector
from ping3 import ping
import smtplib
from email.mime.text import MIMEText

def dbConnect():
    db_config = {
        'host':'localhost',  # e.g., "localhost"
        'user': 'ssadminuser',
        'password' : 'Password1',
        'database' : 'sdash2'
    }
    try:
        dbconnection = mysql.connector.connect(**db_config)
        if dbconnection.is_connected():
            print("Connection successful!")
        return dbconnection
    except mysql.connector.Error as err:
        return None

def ping_ip(ip_address, attempts=5):
    """Ping an IP address multiple times and calculate the response rate."""
    success_count = sum(1 for _ in range(attempts) if ping(ip_address, timeout=1))
    return (success_count / attempts) * 100


def send_email_notification():
    # Email settings
    sender_email = '***@we.utt.edu.tt'
    sender_password = '***'
    recipient_email = '***@we.utt.edu.tt'
    smtp_server = 'smtp.office365.com'
    smtp_port = 587

    try:
        db_connected = dbConnect()
        cursor = db_connected.cursor(dictionary=True)

        # Query the IP address status
        query = "SELECT ip_address, device_status FROM device_list WHERE device_status = 'offline'"
        cursor.execute(query)
        results = cursor.fetchall()

        if results:
            # Construct the email content
            message_body = "The following IP address(es) have changed their status to 'offline':\n\n"
            for row in results:
                message_body += f"IP Address: {row['ip_address']}\n"

            msg = MIMEText(message_body)
            msg['Subject'] = 'IP Address Status Alert'
            msg['From'] = sender_email
            msg['To'] = recipient_email

            # Send the email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)

            print("Email sent successfully.")

        else:
            print("No IP addresses are offline.")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'database' in locals() and database.is_connected():
            database.close()

def update_device_device_status():
    """Connect to the database, check IPs, and update their device_status."""
    try:
        # Connect to the MySQL database
        db_connected = dbConnect()
        cursor = db_connected.cursor()

        # Query to retrieve IP addresses
        select_query = "SELECT ip_address FROM device_list"
        cursor.execute(select_query)
        devices = cursor.fetchall()

        for device in devices:
            ip_address = device[0]
            response_rate = ping_ip(ip_address)

            device_status = 'Online' if response_rate > 75 else 'Offline'

            # Update device_status in the database
            update_query = "UPDATE device_list SET device_status = %s WHERE ip_address = %s"
            cursor.execute(update_query, (device_status, ip_address))

        # Commit changes and close the database
        db_connected.commit()
    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        db_connected.close()


# Call the function
# send_email_notification()

# Call the function
update_device_device_status()
