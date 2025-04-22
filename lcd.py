import smbus2
import time
from RPLCD.i2c import CharLCD

# Initialize the LCD
lcd = CharLCD('PCF8574', 0x27)  # Replace 0x27 with your LCD's I2C address

# Display text
lcd.write_string("Hello, Raspberry Pi!")
time.sleep(10)
lcd.clear()

lcd.write_string("I am a robot")
time.sleep(10)
lcd.clear()

lcd.write_string("I am a good robot")
time.sleep(10)

# Clear the display
lcd.clear()
