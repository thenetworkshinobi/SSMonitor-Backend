import mysql.connector
from ping3 import ping
import smtplib
from email.mime.text import MIMEText
import os

def dbConnect():
    """Establish a connection to the database."""
    db_config = {
        'host': 'localhost',
        'user': 'ssadminuser',
        'password': 'Password1',
        'database': 'ssmonitor'
    }
    try:
        dbconnection = mysql.connector.connect(**db_config)
        if dbconnection.is_connected():
            print("Connection successful!")
        return dbconnection
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

def ping_ip(ip_address, attempts=5):
    """Ping an IP address multiple times and calculate the response rate."""
    success_count = 0
    for _ in range(attempts):
        try:
            response = ping(ip_address, timeout=2)
            if response is not None:
                success_count += 1
        except Exception as e:
            print(f"Error pinging {ip_address}: {e}")
    return (success_count / attempts) * 100

def send_email_notification():
    """Send email alerts for devices that are offline."""
    sender_email = os.getenv('SENDER_EMAIL')
    sender_password = os.getenv('SENDER_PASSWORD')
    recipient_email = '***@we.utt.edu.tt'
    smtp_server = 'smtp.office365.com'
    smtp_port = 587

    try:
        db_connected = dbConnect()
        if not db_connected:
            return

        cursor = db_connected.cursor()

        query = """
        SELECT ip_address FROM device d
        JOIN device_status ds ON d.deviceID = ds.deviceID
        WHERE ds.statusID = 1
        """
        cursor.execute(query)
        results = cursor.fetchall()

        if results:
            message_body = "The following IP address(es) are offline:\n\n"
            for row in results:
                message_body += f"IP Address: {row[0]}\n"

            msg = MIMEText(message_body)
            msg['Subject'] = 'IP Address Status Alert'
            msg['From'] = sender_email
            msg['To'] = recipient_email

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(sender_email, sender_password)
                server.send_message(msg)

            print("Email sent successfully.")
        else:
            print("No IP addresses are offline.")

    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        if cursor:
            cursor.close()
        if db_connected and db_connected.is_connected():
            db_connected.close()

def update_device_device_status():
    """Update the device_status table based on ping results."""
    try:
        db_connected = dbConnect()
        if not db_connected:
            return

        cursor = db_connected.cursor()

        select_query = "SELECT deviceID, ip_address FROM device"
        cursor.execute(select_query)
        deviceList = cursor.fetchall()

        for device in deviceList:
            ip_address = device[1]
            deviceID = device[0]

            response_rate = ping_ip(ip_address)
            status_update = 2 if response_rate >= 75 else 1

            update_query = """
            INSERT INTO device_status (deviceID, statusID, updateTime)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            """
            cursor.execute(update_query, (deviceID, status_update))

        db_connected.commit()
        print("Device statuses updated successfully.")

    except Exception as e:
        print(f"Error occurred: {e}")
    finally:
        if cursor:
            cursor.close()
        if db_connected and db_connected.is_connected():
            db_connected.close()

# Call the function
update_device_device_status()