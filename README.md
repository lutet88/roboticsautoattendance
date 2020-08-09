# Robotics Automatic Attendance System
### SAS One Degree North, 2020

#### Hardware:
Orange Pi Lite2
Waveshare 1.8" 160x128 TFT LCD
Generic PN532 Breakout (or any one with UART)
some random buzzer i had

#### Required Libraries:
(python 3.7+)
- OPi.GPIO
- gspread
- oauth2client
- PIL (pillow imaging)
- ST7735

(other)
- libnfc (pn532-tamashell)
- WiringPi

#### Files
- main.py
main python script.
- SASCard-read.sh
pn53x-tamashell script to scrape response from PN532 after reading ISO14443-4B cards.
- getRx.awk
very smol awk script for formatting
- data folder
contains all fonts, assets for ST7735 to display
