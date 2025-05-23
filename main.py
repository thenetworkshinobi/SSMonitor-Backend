import adafruit_dht
import board
import mysql.connector
from ping3 import ping
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import json
import subprocess
from easysnmp import Session, EasySNMPTimeoutError, EasySNMPError
import winrm
from RPLCD.i2c import CharLCD
import asyncio
import requests

# Set Temperature and Humidity Sensor Pin
dhtdevice = adafruit_dht.DHT11(board.D17)
# Dictionary to track the last email sent time for each device
last_email_sent = {}
# LCD initialization
lcd = CharLCD('PCF8574', 0x27)  # Replace 0x27 with your LCD's I2C address

last_temp_update = None

#Establish database conncection
def dbConnect():
    """Establish a connection to the database."""
    try:
        db_config = load_config("db-config.json")
        dbconnection = mysql.connector.connect(**db_config)
        if dbconnection.is_connected():
            print("Connection successful!")
        return dbconnection
    except mysql.connector.Error as err:
        print(f"Database connection error: {err}")
        return None

# Recieve IP address and return percentage of succesfull pings
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

# Get SMTP config date from JSON file
def load_config(config_file):
    """Load SMTP configuration from a JSON file."""
    try:
        with open(config_file, 'r') as file:
            config = json.load(file)
        return config
    except Exception as e:
        print(f"Error loading SMTP configuration: {e}")
        return None

# Determine if deivce status changed to offline and return list of devices
def get_device_status_changes():
    current_time = time.time()
    offline_devices_alert = [] # List to store devices eligible for email
    """Retrieve device status changes where devices went offline."""
    try:
        db_connected = dbConnect()
        if not db_connected:
            print(f"Failed to connect to database")
            return None

        cursor = db_connected.cursor()

        # Query devices that were online and are now offline
        query = """
        SELECT DISTINCT  d.hostname, d.ip_address FROM  device_status AS ds_current
        JOIN  device AS d ON ds_current.deviceID = d.deviceID
        WHERE ds_current.statusID = 2 -- Device is currently offline
        AND ds_current.updateTime = (SELECT MAX(ds_inner.updateTime)
        FROM device_status AS ds_inner
        WHERE ds_inner.deviceID = ds_current.deviceID) -- Ensure we are checking the latest status
        AND EXISTS (SELECT 1 FROM device_status AS ds_previous
        WHERE ds_previous.deviceID = ds_current.deviceID
        AND ds_previous.statusID IN (1, 3) -- Device was either unknown or online
        AND ds_previous.updateTime < ds_current.updateTime);
        """
        cursor.execute(query)
        ip_results = cursor.fetchall()
        #print(ip_results)
        
        if ip_results:
            for row in ip_results:
                hostname = row[0]
                ip_address = row[1]
                device_identifier = f"{hostname}-{ip_address}"

                # Check if the device has already sent an email in the past x minutes
                
                if device_identifier in last_email_sent:
                    last_sent_time = last_email_sent[device_identifier]
                    if current_time - last_sent_time < 120:  # 1 minutes = 60 seconds
                        continue

                    offline_devices_alert.append(row)
                
                # Update the last sent time for this device
                last_email_sent[device_identifier] = current_time                
                
        return offline_devices_alert

    except Exception as e:
        print(f"Error while fetching data: {e}")
        return None

    finally:
        if cursor:
            cursor.close()
        if db_connected and db_connected.is_connected():
            db_connected.close()

# Generic email sender function
def send_email(subject, message_body):
    
    """Send email alerts for device status changes."""
    smtp_config = load_config("smtp-config.json")
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
        except Exception as e:
            print(f"Error while sending admin emails: {e}")
            return False
        finally:
            print(f"Email sent successfully to {to_email} with subject: {subject}")
            return True

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

async def notification_handler(offline_devices_alert=None, temperature=None):
    """
    Handles email notifications based on ip_results or temperature.

    Parameters:
        offline_devices_alert (list): List of devices that went offline, with (hostname, ip_address).
        temperature (float): Current temperature value to check if > 20°C.
    """
    # Notify about offline devices
    if offline_devices_alert:
        subject = "Device(s) Status Changed: Offline"
        message_body = "The following device(s) is offline:"
        for hostname, ip_address in offline_devices_alert:
            message_body += f"\nHostname: {hostname} | IP Address: {ip_address}"    
        message_body += f"\n\nPlease take immediate action!"
        send_email(subject, message_body)
        play_alert(message_body)

    # Notify about high temperature
    if temperature is not None and temperature > 20:
        subject = "Temperature Alert: High Temperature Detected"
        message_body = f"Warning: The recorded temperature is {temperature}°C, which exceeds the threshold of 20°C.\n\nPlease investigate the issue immediately."
        send_email(subject, message_body)
        play_alert(message_body)
    
# Update Current device status
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

# Get Temp and Humididy, update database and output temp data
def update_temp_humidity():
    global last_temp_update
    current_time = time.time()
    
    max_retries = 3
    retry_count = 0
    temperature_c = None
    humidity = None

    while retry_count < max_retries:
        try:
            temperature_c = dhtdevice.temperature
            humidity = dhtdevice.humidity
            if humidity is not None and temperature_c is not None:
                break     
        except RuntimeError as error:
            print(f"Attempt Unable to read Temnp and Humdity: {error.args[0]}")
            time.sleep(1.0)
        retry_count += 1

    if humidity is not None and temperature_c is not None:
        print("Temp={0:0.1f}C  Humidity={1:0.1f}%".format(temperature_c, humidity))
        try:
            db_connected = dbConnect()
            if not db_connected:
                return

            cursor = db_connected.cursor()

            update_query = """
            INSERT INTO environment (temperature, humidity)
            VALUES (%s, %s)
            """
            cursor.execute(update_query, (temperature_c, humidity))

            db_connected.commit()
            print("Environment Data updated successfully.")
        except Exception as e:
            print(f"Error occurred: {e}")
            print("Environment Data NOT updated successfully.")
        finally:
            if cursor:
                cursor.close()
            if db_connected and db_connected.is_connected():
                db_connected.close()
            if last_temp_update and (current_time - last_temp_update < 120):
                return None
            last_temp_update = current_time   
        return temperature_c        
    else:
        print("Sensor failure. Check wiring.")

# Get SNMP data for IP
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

# Get WMI data from IP
def get_wmi_data(ip):
    """Fetch data from Windows devices using PyWinRM."""
    try:
        # Create a WinRM session
        session = winrm.Session(f'http://{ip}:5985/wsman', auth=('ssmonitor', 'Password1'), transport='ntlm')
        print(f"Fetching data for IP: {ip}.")
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
        network_in_query = 'Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface | Select-Object -ExpandProperty BytesReceivedPerSec'
        network_in_throughput_result = session.run_ps(network_in_query)
        network_in_throughput = network_in_throughput_result.std_out.decode().strip() if network_in_throughput_result.std_out else None
        network_out_query = 'Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface | Select-Object -ExpandProperty BytesSentPerSec'
        network_out_throughput_result = session.run_ps(network_out_query)
        network_out_throughput = network_out_throughput_result.std_out.decode().strip() if network_out_throughput_result.std_out else None

        # Calculate RAM usage percentage
        total_ram_value = int(total_ram)
        used_ram_value = int(used_ram)
        ram_usage_percentage = (used_ram_value / total_ram_value) * 100

        # Convert network throughput to MB/s
        network_in_throughput_mbps = convert_bps_to_mbps(int(network_in_throughput))
        network_out_throughput_mbps = convert_bps_to_mbps(int(network_out_throughput))

        return {
            "cpu_usage": cpu_usage,
            "ram_total": total_ram,
            "ram_available": used_ram,
            "ram_usage_percentage": f"{ram_usage_percentage:.2f}",
            "network_in_throughput": network_in_throughput_mbps,
            "network_out_throughput": network_out_throughput_mbps
        }
    except Exception as e:
        print(f"Error fetching data for IP: {ip}. {e}")
        return {
            "cpu_usage": "0",
            "ram_total": "0",
            "ram_available": "0",
            "ram_usage_percentage": "0",
            "network_in_throughput": "0",
            "network_out_throughput": "0"            
        }

# Converter
def convert_bps_to_mbps(bps):
    """Convert network throughput from bps to MB/s."""
    if bps is None or bps == "Unavailable":
        return "Unavailable"
    try:
        mbps = round(bps / 1_000_000,2)  # Convert bps to mb/s
        return f"{mbps:.2f}"  # Format to 2 decimal places
    except Exception as e:
        print(f"Error during conversion: {e}")
        return "Unavailable"

# Calculte the network through put using 2 requests
def calculate_throughput(ip, community, oid, interval=1):
    try:
        first = int(get_snmp_data(ip, community, oid))    
        if first is None or first == "NOSUCHINSTANCE":
            first = 0
        time.sleep(interval)
        second = int(get_snmp_data(ip, community, oid))
        if second is None or second == "NOSUCHINSTANCE":
            second = 0
        delta = second - first
        if delta < 0:
            # Handle counter rollover
            delta = (2**32 - first) + second
        return delta
    except Exception as e:
        print(f"Error calculating throughput for IP {ip}: {e}")
        return 0
    
# Request SNMP data and send to website
async def get_realtime_data():    
    
    # Fetch IP addresses from the database and collect SNMP data for Linux devices.
    for _ in range(10):
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
            ram_total_oid = ".1.3.6.1.4.1.2021.4.5.0"  # Total RAM OID
            ram_available_oid = ".1.3.6.1.4.1.2021.4.3.0"   # Used RAM OID
            cpu_oid = ".1.3.6.1.4.1.2021.11.11.0"    # Example OID for CPU idle percentage
            network_in_oid = ".1.3.6.1.2.1.2.2.1.10.2"    # Example OID for network in throughput
            network_out_oid = ".1.3.6.1.2.1.2.2.1.16.2"    # Example OID for network out throughput

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
                        cpu_usage = 100 - int(get_snmp_data(ip, community, cpu_oid))
                        ram_total = int(get_snmp_data(ip, community, ram_total_oid))
                        ram_available = int(get_snmp_data(ip, community, ram_available_oid))
                        network_in_throughput_bps = int(calculate_throughput(ip, community, network_in_oid))
                        network_out_throughput_bps = int(calculate_throughput(ip, community, network_out_oid))
                        network_in_throughput = convert_bps_to_mbps(network_in_throughput_bps) if network_in_throughput_bps else 0
                        network_out_throughput = convert_bps_to_mbps(network_out_throughput_bps) if network_out_throughput_bps else 0
                                                                
                        # Calculate RAM usage percentage
                        if ram_total and ram_available:
                            ram_usage_percentage = ((ram_total - ram_available)/ram_total) * 100
                        else:
                            ram_usage_percentage = 0
                        
                        # Append data to list
                        stat_devices_data.append({
                            "ip_address": ip,
                            "cpu_usage": f"{cpu_usage}" if cpu_usage is not None else 0,
                            "ram_usage_percentage": f"{ram_usage_percentage:.2f}" if isinstance(ram_usage_percentage, float) else ram_usage_percentage,
                            "network_in_throughput": f"{network_in_throughput}" if network_in_throughput is not None else 0,
                            "network_out_throughput": f"{network_out_throughput}" if network_out_throughput is not None else 0
                        })
                    if os == 'windows' and status == 'online':
                        # Fetch WMI data for Windows devices
                        print(f"Fetching WMI data for IP: {ip}")
                        wmi_data = get_wmi_data(ip)
                        
                        stat_devices_data.append({
                            "ip_address": ip,
                            "cpu_usage": wmi_data["cpu_usage"],
                            "ram_usage_percentage": f"{wmi_data['ram_usage_percentage']:.2f}" if isinstance(wmi_data["ram_usage_percentage"], float) else wmi_data["ram_usage_percentage"],
                            "network_in_throughput": wmi_data["network_in_throughput"],
                            "network_out_throughput": wmi_data["network_out_throughput"]
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
            await asyncio.sleep(1)
        except mysql.connector.Error as err:
            print(f"Database query error: {err}")
        finally:
            cursor.close()
            db_connection.close()
            print("Database connection closed.")

# Display current status of devices on LCD
async def display_device_status():
    #for _ in range(10):
        # Database connection
    try:
        db_connected = dbConnect()
        if not db_connected:
            return
        cursor = db_connected.cursor(dictionary=True)

        # Query the recent_device_status view
        query = "SELECT hostname, ip_address, latest_status FROM recent_device_status"
        cursor.execute(query)
        rows = cursor.fetchall()

        # Display each row on the LCD
        for row in rows:
            lcd.clear()
            lcd.cursor_pos = (0,0)
            # Display hostname and IP address on the first line
            lcd.write_string(f"Host: {row['hostname'][:16]}")  # Limit to 16 characters
            lcd.cursor_pos = (1,0)
            # Display status on the second line
            lcd.write_string(f"IP: {row['ip_address'][:16]}")  # Limit to 16 characters
            await asyncio.sleep(4) 
            
            lcd.clear()
            lcd.cursor_pos = (0,0)
            lcd.write_string(f"Host: {row['hostname'][:16]}")  # Limit to 16 characters
            lcd.cursor_pos = (1,0)           
            lcd.write_string(f"Status: {row['latest_status'][:16]}")  # Limit to 16 characters
            await asyncio.sleep(4) 

        # Display temperature and humdity
        query = "SELECT temperature, humidity FROM environment ORDER BY updateTime DESC LIMIT 1"
        cursor.execute(query)
        row = cursor.fetchone()
        lcd.clear()
        lcd.cursor_pos = (0,0)
        lcd.write_string(f"Temp: {row['temperature']} C")  # Limit to 16 characters
        lcd.cursor_pos = (1,0)
        lcd.write_string(f"Humdity: {row['humidity']} %")  # Limit to 16 characters
        await asyncio.sleep(5) 
    except mysql.connector.Error as err:
        print(f"Error: {err}")
    finally:
        if db_connected.is_connected():
            cursor.close()
            db_connected.close()
            lcd.clear()
            print(f"Displayed Device Status on LCD")   

# Text to Speech Audio Alert
def play_alert(message, model_path="/home/ssmonitor/ssagent/voices/en_GB-alan-medium.onnx"):
   
    output_wav = "/tmp/tts_output.wav"
    print(f"Audio Alert:", message)
    try:
        result = subprocess.run(
            ["piper", "--model", model_path, "--output_file", output_wav],
            input=message.encode("utf-8"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        if result.returncode != 0:
            print("TTS error:", result.stderr.decode())
            return

        # Play audio via ALSA (WM8960)
        subprocess.run(["aplay", output_wav])

    except Exception as e:
        print(f"Error during Text to Speech or playback: {e}")
    finally:
        if os.path.exists(output_wav):
            os.remove(output_wav)
            
# Call the function
async def main():
    try:
        while True:
            start_time = time.time()
            #update_device_device_status()
            
            await get_realtime_data()  # Use await for async functions                        
            #offline_devices_alert = get_device_status_changes()
            #temperature = update_temp_humidity()
            #await notification_handler(offline_devices_alert=offline_devices_alert, temperature=temperature)
            
            #await display_device_status()
            #await asyncio.sleep(10)  # Async sleep instead of time.sleep()
            elapsed_time = time.time() - start_time
            if elapsed_time < 10:
                await asyncio.sleep(10 - elapsed_time)
    except KeyboardInterrupt:
        print("Stopping...")
        
if __name__ == "__main__":
    asyncio.run(main())


