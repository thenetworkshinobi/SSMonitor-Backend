import mysql.connector
import json
from easysnmp import Session, EasySNMPTimeoutError, EasySNMPError

def db_connect():
    """Establish a connection to the MySQL database."""
    db_config = {
        'host': 'localhost',
        'user': 'ssadminuser',
        'password': 'Password1',
        'database': 'ssmonitor'
    }
    try:
        connection = mysql.connector.connect(**db_config)
        if connection.is_connected():
            print("Database connection established!")
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        return None

def get_snmp_data(ip, community, oid):
    """Fetch data from SNMP using EasySNMP."""
    try:
        # Create an SNMP session
        session = Session(hostname=ip, community=community, version=2)
        # Fetch the value for the OID
        result = session.get(oid)
        return result.value
    except EasySNMPTimeoutError:
        print(f"SNMP request timed out for IP: {ip}")
        return "Unavailable"
    except EasySNMPError as e:
        print(f"SNMP request failed for IP: {ip} with error: {e}")
        return "Unavailable"

def get_device_status():
    """Fetch IP addresses from the database and collect SNMP data for Linux devices."""
    # Connect to the database
    connection = db_connect()
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
        cpu_oid = ".1.3.6.1.4.1.2021.10.1.3.1"  # Example OID for CPU usage
        ram_oid = "1.3.6.1.4.1.2021.4.6.0"   # Example OID for RAM usage
        network_oid = "1.3.6.1.2.1.2.2.1.10.1"  # Example OID for network throughput

        # Collect data for Linux devices
        linux_devices_data = []
        for device in devices:
            if device['os'].lower() == 'linux':
                ip = device['ip_address']
                print(f"Fetching SNMP data for IP: {ip}")

                cpu_usage = get_snmp_data(ip, community, cpu_oid)
                ram_usage = get_snmp_data(ip, community, ram_oid)
                network_throughput = get_snmp_data(ip, community, network_oid)

                linux_devices_data.append({
                    "ip_address": ip,
                    "cpu_usage": cpu_usage,
                    "ram_usage": ram_usage,
                    "network_throughput": network_throughput
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

# Execute the function
if __name__ == "__main__":
    get_device_status()
