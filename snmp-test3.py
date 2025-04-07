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

# Execute the function
if __name__ == "__main__":
    get_device_status()
