import mysql.connector
from ping3 import ping

def ping_ip(ip_address, attempts=5):
    """Ping an IP address multiple times and calculate the response rate."""
    success_count = sum(1 for _ in range(attempts) if ping(ip_address, timeout=1))
    return (success_count / attempts) * 100

def update_device_device_status():
    """Connect to the database, check IPs, and update their device_status."""
    # Connect to the MySQL database
    connection = mysql.connector.connect(
        host="localhost",  # e.g., "localhost"
        user="ssadminuser",
        password="Password1",
        database="sdash2"
    )
    cursor = connection.cursor()

    # Query to retrieve IP addresses
    select_query = "SELECT ip_address FROM device_list"
    cursor.execute(select_query)
    devices = cursor.fetchall()

    for device in devices:
        ip_address = device[0]
        response_rate = ping_ip(ip_address)

        device_status = 'Online' if response_rate > 75 else 'offline'

        # Update device_status in the database
        update_query = "UPDATE device_list SET device_status = %s WHERE ip_address = %s"
        cursor.execute(update_query, (device_status, ip_address))

    # Commit changes and close the connection
    connection.commit()
    connection.close()

# Call the function
update_device_device_status()
