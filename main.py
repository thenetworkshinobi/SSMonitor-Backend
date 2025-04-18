#import adafruit_dht
import mysql.connector
from ping3 import ping
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
#import board
import json
from easysnmp import Session, EasySNMPTimeoutError, EasySNMPError
import winrm
from RPLCD.i2c import CharLCD
import asyncio
import requests


def dbConnect():
    """Establish a connection to the database."""
    db_config = {
        'host': '192.168.100.131',
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
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def load_smtp_config(config_file):
    """Load SMTP configuration from a JSON file."""
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
        return config
    except Exception as e:
        print(f"Error loading SMTP configuration: {e}")
        return None

def send_email_notification():
    """Send email alerts for devices that are offline."""
    smtp_config = load_smtp_config("smtp-config.json")
    if not smtp_config:
        print("Failed to load SMTP configuration")
        return

    try:
        db_connected = dbConnect()
        if not db_connected:
            return

        cursor = db_connected.cursor()

        query = """
        SELECT ip_address, hostname FROM device d

        JOIN device_status ds ON d.deviceID = ds.deviceID
        WHERE ds.statusID = 1
        """
        cursor.execute(query)
        ip_results = cursor.fetchall()
        
        query = "SELECT email FROM adminuser"
        cursor.execute(query)
        email_results = cursor.fetchall()
        to_email = [row[0] for row in email_results] 

        if ip_results:
            subject = "Device(s) Down"
            message_body = "The following IP address(es) are offline:\n\n"
            for row in ip_results:
                message_body += f"Hostname: {row[1]} IP Address: {row[0]}\n"

            msg = MIMEText(message_body)
            msg['FROM'] = smtp_config['sender_email']
            msg['To'] = "," .join(to_email) 
            msg['Subject'] = subject
            msg.attach(MIMEText(message_body, 'plain'))
            

            with smtplib.SMTP(smtp_config['smtp_server'], smtp_config['port']) as server:

                server.starttls()
                server.login(smtp_config['sender_email'], smtp_config['sender_password'])
                server.sendmail(smtp_config['sender_email'], to_email, msg.astring())

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
        return "0"
    except EasySNMPError as e:
        print(f"SNMP request failed for IP: {ip} with error: {e}")
        return "0"


def get_wmi_data(ip):
    """Fetch data from Windows devices using PyWinRM."""
    try:
        # Create a WinRM session
        session = winrm.Session(f'http://{ip}:5985/wsman', auth=('ssmonitor', 'Password1'))  # Replace with actual credentials
        print(f"Fetching data for IP: {ip}. Exception: {e}")
        # Query Windows device for CPU usage
        cpu_query = 'Get-WmiObject -Query "SELECT LoadPercentage FROM Win32_Processor" | Select-Object -ExpandProperty LoadPercentage'
        cpu_usage_result = session.run_ps(cpu_query)
        cpu_usage = cpu_usage_result.std_out.decode().strip()

        # Query Windows device for total and used RAM
        ram_query = """
        $computerSystem = Get-WmiObject Win32_ComputerSystem
        $os = Get-WmiObject Win32_OperatingSystem
        [PSCustomObject]@{
            TotalRam = $computerSystem.TotalPhysicalMemory
            UsedRam = ($computerSystem.TotalPhysicalMemory - $os.FreePhysicalMemory * 1024)
        }
        """
        ram_usage_result = session.run_ps(ram_query)
        ram_data = ram_usage_result.std_out.decode().strip().splitlines()
        total_ram = ram_data[0].split(":")[1].strip()
        used_ram = ram_data[1].split(":")[1].strip()

        # Query Windows device for network throughput
        network_query = 'Get-WmiObject -Query "SELECT BytesReceivedPerSec FROM Win32_PerfFormattedData_Tcpip_NetworkInterface" | Select-Object -ExpandProperty BytesReceivedPerSec'
        network_throughput_result = session.run_ps(network_query)
        network_throughput = network_throughput_result.std_out.decode().strip()

        # Calculate RAM usage percentage
        total_ram_value = int(total_ram)
        used_ram_value = int(used_ram)
        ram_usage_percentage = (used_ram_value / total_ram_value) * 100

        # Convert network throughput to MB/s
        network_throughput = convert_bps_to_mbps(int(network_throughput))

        return {
            "cpu_usage": cpu_usage,
            "ram_total": total_ram,
            "ram_used": used_ram,
            "ram_usage_percentage": f"{ram_usage_percentage:.2f}",
            "network_throughput": network_throughput
        }
    except Exception as e:
        print(f"Error fetching data for IP: {ip}. Exception: {e}")
        return {
            "cpu_usage": "0",
            "ram_total": "0",
            "ram_used": "0",
            "ram_usage_percentage": "0",
            "network_throughput": "0"
        }


def convert_bps_to_mbps(bps):
    """Convert network throughput from bps to MB/s."""
    if bps is None or bps == "Unavailable":
        return "Unavailable"
    try:
        mbps = bps / (1_048_576)  # Convert bps to mb/s
        return f"{mbps:.2f}"  # Format to 2 decimal places
    except Exception as e:
        print(f"Error during conversion: {e}")
        return "Unavailable"

def get_realtime_data():
    """Fetch IP addresses from the database and collect SNMP data for Linux devices."""
    # Connect to the database
    db_connection = dbConnect()
    if db_connection is None:
        print("Failed to connect to the database. Exiting.")
        return

    try:
        # Fetch IP addresses and device types
        cursor = db_connection.cursor(dictionary=True)
        query = "SELECT ip_address, os, rfc1918, latest_status FROM recent_device_status"
        cursor.execute(query)
        devices = cursor.fetchall()

        # SNMP community string and OIDs
        community = "ssmonitor"
        ram_total_oid = "1.3.6.1.4.1.2021.4.5.0"  # Total RAM OID
        ram_used_oid = "1.3.6.1.4.1.2021.4.6.0"   # Used RAM OID
        cpu_oid = ".1.3.6.1.4.1.2021.10.1.3.1"    # Example OID for CPU usage
        network_oid = "1.3.6.1.2.1.2.2.1.10.1"    # Example OID for network throughput

        # Collect data for Linux devices
        stat_devices_data = []
        for device in devices:
            rfc1918 = device.get('rfc1918')
            ip = device.get('ip_address')
            os = device.get('os', '').lower()
            status = device.get('latest_status').lower()
            if rfc1918 and ip:              
                if os == 'linux' and status == 'online':
                    print(f"Fetching SNMP data for IP: {ip}")
                    # Fetch SNMP data
                    cpu_usage = get_snmp_data(ip, community, cpu_oid)
                    ram_total = int(get_snmp_data(ip, community, ram_total_oid))
                    ram_used = int(get_snmp_data(ip, community, ram_used_oid))
                    network_throughput_bps = int(get_snmp_data(ip, community, network_oid))
                    network_throughput = convert_bps_to_mbps(network_throughput_bps) if network_throughput_bps else "0"

                    if ram_total and ram_used:
                        ram_usage_percentage = (ram_used / ram_total) * 100
                    else:
                        ram_usage_percentage = "0"
                                        
                    # Calculate RAM usage percentage
                    if ram_total and ram_used:
                        ram_usage_percentage = (ram_used / ram_total) * 100
                    else:
                        ram_usage_percentage = "0"
                    
                    # Append data to list
                    stat_devices_data.append({
                        "ip_address": ip,
                        "cpu_usage": f"{cpu_usage}" if cpu_usage is not None else "0",
                        "ram_total": f"{ram_total}" if ram_total is not None else "0",
                        "ram_used": f"{ram_used}" if ram_used is not None else "0",
                        "ram_usage_percentage": f"{ram_usage_percentage:.2f}" if isinstance(ram_usage_percentage, float) else ram_usage_percentage,
                        "network_throughput": f"{network_throughput}" if network_throughput is not None else "0"
                    })
                elif os == 'windows' and status == 'online':
                    # Fetch WMI data for Windows devices
                    print(f"Fetching WMI data for IP: {ip}")
                    wmi_data = get_wmi_data(ip)
                    
                    stat_devices_data.append({
                        "ip_address": ip,
                        "cpu_usage": wmi_data["cpu_usage"],
                        "ram_total": wmi_data["ram_total"],
                        "ram_used": wmi_data["ram_used"],
                        "ram_usage_percentage": f"{wmi_data['ram_usage_percentage']:.2f}" if isinstance(wmi_data["ram_usage_percentage"], float) else wmi_data["ram_usage_percentage"],
                        "network_throughput": wmi_data["network_throughput"]
                    })

        # Write output to JSON file
        with open("/home/ssmonitor/ssagent/devices_data.json", "w") as json_file:
            json.dump(stat_devices_data, json_file, indent=4)
        
        # File path to the JSON file
        json_file_path = "/home/ssmonitor/ssagent/devices_data.json"
        
        # Load the JSON data
        #with open(json_file_path, 'r') as file:
        #    json_data = json.load(file)
        
        # URL of the receiver script
        url = "http://192.168.100.131/ssmonitor/reciever.php"

        # Send the JSON data as a POST request
        response = requests.post(url, json = stat_devices_data)

        # Print the server's response
        print(f"Server response: {response.text}")
           
        print("Data has been written to devices_data.json!")
        time.sleep(1)
    except mysql.connector.Error as err:
        print(f"Database query error: {err}")
    finally:
        cursor.close()
        db_connection.close()
        print("Database connection closed.")

def display_device_status():
    # LCD initialization
    lcd = CharLCD('PCF8574', 0x27)  # Replace 0x27 with your LCD's I2C address

    # Database connection
    try:
        db_connected = dbConnect()
        if not db_connected:
            return
        cursor = db_connected(dictionary=True)

        # Query the recent_device_status view
        query = "SELECT hostname, ip_address, latest_status FROM recent_device_status"
        cursor.execute(query)
        rows = cursor.fetchall()

        # Display each row on the LCD
        for row in rows:
            lcd.clear()
            # Display hostname and IP address on the first line
            lcd.write_string(f"Host: {row['hostname'][:16]}")  # Limit to 16 characters
            lcd.cursor_pos = (1,0)
            # Display status on the second line
            lcd.write_string(f"IP: {row['ip_address'][:16]}")  # Limit to 16 characters
            time.sleep(2)
            
            lcd.clear()
            lcd.write_string(f"Host: {row['hostname'][:16]}")  # Limit to 16 characters
            lcd.cursor_pos = (1,0)           
            lcd.write_string(f"Status: {row['latest_status'][:16]}")  # Limit to 16 characters
            time.sleep(4)

    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if db.is_connected():
            cursor.close()
            db.close()
        lcd.clear()
        lcd.write_string("Done!")
        time.sleep(10)
        lcd.clear()
        
# Call the function
def main():
    try:
        while True:
            update_device_device_status()
            #update_temp_humidity()
            get_realtime_data()
            #display_device_status()
            time.sleep(10)
    except KeyboardInterrupt:
        print("Stopping...")
        
if __name__ == "__main__":
    main()


