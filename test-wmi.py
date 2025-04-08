def process_devices():
    """Fetch IP addresses from the database and collect device data (SNMP for Linux, WMI for Windows)."""
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

        # SNMP community string and OIDs for Linux devices
        community = "ssmonitor"
        ram_total_oid = "1.3.6.1.4.1.2021.4.5.0"
        ram_used_oid = "1.3.6.1.4.1.2021.4.6.0"
        cpu_oid = ".1.3.6.1.4.1.2021.10.1.3.1"
        network_oid = "1.3.6.1.2.1.2.2.1.10.1"

        devices_data = []

        for device in devices:
            ip = device['ip_address']
            os_type = device['os'].lower()
            local = device['rfc1918']

            if os_type != 'windows' & local == True:
                print(f"Fetching SNMP data for IP: {ip}")
                cpu_usage = get_snmp_data(ip, community, cpu_oid)
                ram_total = int(get_snmp_data(ip, community, ram_total_oid))
                ram_used = int(get_snmp_data(ip, community, ram_used_oid))
                network_throughput_bps = int(get_snmp_data(ip, community, network_oid))
                network_throughput = convert_bps_to_mbps(network_throughput_bps) if network_throughput_bps else "Unavailable"

                ram_usage_percentage = (ram_used / ram_total) * 100 if ram_total and ram_used else "Unavailable"

                devices_data.append({
                    "ip_address": ip,
                    "os": "Linux",
                    "cpu_usage": f"{cpu_usage}" if cpu_usage is not None else "Unavailable",
                    "ram_total": f"{ram_total}" if ram_total is not None else "Unavailable",
                    "ram_used": f"{ram_used}" if ram_used is not None else "Unavailable",
                    "ram_usage_percentage": f"{ram_usage_percentage:.2f}" if isinstance(ram_usage_percentage, float) else ram_usage_percentage,
                    "network_throughput": f"{network_throughput}" if network_throughput is not None else "Unavailable"
                })

            elif os_type == 'windows' & local == True:
                print(f"Fetching WMI data for Windows IP: {ip}")
                try:
                    import wmi
                    wmi_obj = wmi.WMI(computer=ip)
                    cpu = wmi_obj.Win32_Processor()[0].LoadPercentage
                    total_ram = int(wmi_obj.Win32_ComputerSystem()[0].TotalPhysicalMemory) / (1024 ** 2)
                    free_ram = int(wmi_obj.Win32_OperatingSystem()[0].FreePhysicalMemory) / 1024
                    used_ram = total_ram - free_ram
                    ram_usage_percentage = (used_ram / total_ram) * 100
                    network = "Unavailable"  # Adjust this based on your network throughput metric

                    devices_data.append({
                        "ip_address": ip,
                        "os": "Windows",
                        "cpu_usage": f"{cpu}" if cpu is not None else "Unavailable",
                        "ram_total": f"{total_ram}" if total_ram is not None else "Unavailable",
                        "ram_used": f"{used_ram}" if used_ram is not None else "Unavailable",
                        "ram_usage_percentage": f"{ram_usage_percentage:.2f}" if isinstance(ram_usage_percentage, float) else "Unavailable",
                        "network_throughput": f"{network}" if network is not None else "Unavailable"
                    })

                except Exception as e:
                    print(f"WMI query error for IP {ip}: {e}")

        # Write output to JSON file
        with open("/var/www/html/data/devices_data.json", "w") as json_file:
            json.dump(devices_data, json_file, indent=4)

        print("Data has been written to devices_data.json!")

    except mysql.connector.Error as err:
        print(f"Database query error: {err}")
    finally:
        cursor.close()
        connection.close()
        print("Database connection closed.")