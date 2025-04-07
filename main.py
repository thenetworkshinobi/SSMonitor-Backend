#import adafruit_dht
import mysql.connector
from ping3 import ping
#import smtplib
#from email.mime.text import MIMEText
import os
import time
#import board
import json
from easysnmp import Session, EasySNMPTimeoutError, EasySNMPError

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
            status_update = 3 if response_rate >= 75 else 2

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

def update_temp_humidity():
    dhtdevice = adafruit_dht.DHT11(board.D17, use_pulseio=False)
    try:        
        temperature_c = dhtdevice.temperature
        humidity = dhtdevice.humidity
    except RuntimeError as error:
        # Handle errors (common with DHT sensors)
        print(error.args[0])
        time.sleep(2.0)        
    except Exception as error:
        dhtDevice.exit()
        raise error
    if humidity is not None and temperature_c is not None:
        print("Temp={0:0.1f}C  Humidity={1:0.1f}%".format(temperature_c, humidity))
    else:
        print("Sensor failure. Check wiring.")

def get_snmp_data(ip, community, oid):
    """Fetch data from SNMP using EasySNMP."""
    try:
        # Create an SNMP session
        session = Session(hostname=ip, community=community, version=2)
        # Fetch the value for the OID
        result = session.get(oid)
        return result.value  # Convert to integer for calculation
    except EasySNMPTimeoutError:
        print(f"SNMP request timed out for IP: {ip}")
        return None
    except EasySNMPError as e:
        print(f"SNMP request failed for IP: {ip} with error: {e}")
        return None

def convert_bps_to_mbps(bps):
    """Convert network throughput from bps to MB/s."""
    if bps is None or bps == "Unavailable":
        return "Unavailable"
    try:
        mbps = bps / (8 * 1_048_576)  # Convert bps to MB/s
        return f"{mbps:.2f}"  # Format to 2 decimal places
    except Exception as e:
        print(f"Error during conversion: {e}")
        return "Unavailable"

def process_snmp():
    """Fetch IP addresses from the database and collect SNMP data for Linux devices."""
    # Connect to the database
    connection = dbConnect()
    if connection is None:
        print("Failed to connect to the database. Exiting.")
        return

    try:
        # Fetch IP addresses and device types
        cursor = connection.cursor(dictionary=True)
        query = "SELECT ip_address, os FROM recent_device_status"
        cursor.execute(query)
        devices = cursor.fetchall()

        # SNMP community string and OIDs
        community = "ssmonitor"
        ram_total_oid = "1.3.6.1.4.1.2021.4.5.0"  # Total RAM OID
        ram_used_oid = "1.3.6.1.4.1.2021.4.6.0"   # Used RAM OID
        cpu_oid = ".1.3.6.1.4.1.2021.10.1.3.1"    # Example OID for CPU usage
        network_oid = "1.3.6.1.2.1.2.2.1.10.1"    # Example OID for network throughput

        # Collect data for Linux devices
        linux_devices_data = []
        for device in devices:
            if device['os'].lower() == 'linux':
                ip = device['ip_address']
                print(f"Fetching SNMP data for IP: {ip}")

                # Fetch SNMP data
                cpu_usage = get_snmp_data(ip, community, cpu_oid)
                ram_total = int(get_snmp_data(ip, community, ram_total_oid))
                ram_used = int(get_snmp_data(ip, community, ram_used_oid))
                network_throughput_bps = int(get_snmp_data(ip, community, network_oid))
                network_throughput = convert_bps_to_mbps(network_throughput_bps) if network_throughput_bps else "Unavailable"

                if ram_total is not None and ram_used is not None:
                    ram_total_value = int(ram_total)  # Parse string to integer for calculation
                    ram_used_value = int(ram_used)    # Parse string to integer for calculation
                    ram_usage_percentage = (ram_used_value / ram_total_value) * 100
                else:
                    ram_total_value = ram_used_value = ram_usage_percentage = "Unavailable"
                
                # Calculate RAM usage percentage
                if ram_total and ram_used:
                    ram_usage_percentage = (ram_used / ram_total) * 100
                else:
                    ram_usage_percentage = "Unavailable"
                
                # Append data to list
                linux_devices_data.append({
                    "ip_address": ip,
                    "cpu_usage": f"{cpu_usage}%" if cpu_usage is not None else "Unavailable",
                    "ram_total": f"{ram_total} KB" if ram_total is not None else "Unavailable",
                    "ram_used": f"{ram_used} KB" if ram_used is not None else "Unavailable",
                    "ram_usage_percentage": f"{ram_usage_percentage:.2f}%" if isinstance(ram_usage_percentage, float) else ram_usage_percentage,
                    "network_throughput": f"{network_throughput} MB/s" if network_throughput is not None else "Unavailable"
                })

        # Write output to JSON file
        with open("linux_devices_data.json", "w") as json_file:
            json.dump(linux_devices_data, json_file, indent=4)

        print("Data has been written to linux_devices_data.json!")

    except mysql.connector.Error as err:
        print(f"Database query error: {err}")
    finally:
        cursor.close()
        connection.close()
        print("Database connection closed.")


# Call the function

try:
    while True:
        update_device_device_status()
        #update_temp_humidity()
        process_snmp()
        time.sleep(10)
except KeyboardInterrupt:
    print("Stopping...")