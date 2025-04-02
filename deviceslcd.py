import time
import mysql.connector
from RPLCD.i2c import CharLCD

def display_device_status():
    # LCD initialization
    lcd = CharLCD('PCF8574', 0x27)  # Replace 0x27 with your LCD's I2C address

    # Database connection
    try:
        db = mysql.connector.connect(
            host="localhost",  # Replace with your database host
            user="ssadminuser",  # Replace with your database username
            password="Password1",  # Replace with your database password
            database="ssmonitor"  # Replace with your database name
        )
        cursor = db.cursor(dictionary=True)

        # Query the recent_device_status view
        query = "SELECT hostname, ip_address, latest_status FROM recent_device_status"
        cursor.execute(query)
        rows = cursor.fetchall()

        # Display each row on the LCD
        for row in rows:
            lcd.clear()
            # Display hostname and IP address on the first line
            lcd.write_string(f"Host: {row['hostname'][:16]}")  # Limit to 16 characters
            time.sleep(2)
            lcd.clear()
            lcd.write_string(f"IP: {row['ip_address'][:16]}")  # Limit to 16 characters
            time.sleep(2)
            lcd.clear()
            # Display status on the second line
            lcd.write_string(f"Status: {row['latest_status'][:16]}")  # Limit to 16 characters
            time.sleep(3)

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
display_device_status()
