############################################
# RoboticsAutoAttendance                   # 
# Author: Jefferson Z. (github.com/xhex88) #
# Thanks to: Liam K. (github.com/fillnye)  #
# Version: v0.1a (Aug 9, 2020)             #
############################################

# core
import sys
import threading
import netifaces
import base64

# PN532
import subprocess  # needed to run sh from python and fetch results through processes
import time

# Google Sheets API
import gspread # google spreadsheets api
from oauth2client.service_account import ServiceAccountCredentials # google auth using credentials.json

# Display
from PIL import Image, ImageFont, ImageDraw
import ST7735 as ST7735 # modded for our specific ST7735S Waveshare 1.8"
import OPi.GPIO as GPIO
GPIO.cleanup()

# SQLite
import sqlite3

# Variables
networkinterface='wlan0'
buzzer_pin = 12
bg_filepath = "data/background.jpg"
checkmark_filepath = "data/checkmark.png"
dots_filepath = "data/dots.png"
exit_filepath = "data/exit.png"
user_filepath = "data/user.png"
wheel_filepath = "data/wheel.png"
newuserfail_filepath = "data/nufail.png" 
newuserreg_filepath = "data/urreg.png"
font_filepath = "data/Gontserrat-Light.ttf"
imgrotation = -1 # must be -1 or 1, i just did this because lazy
ipenable = True

# init SQLite
db = sqlite3.connect("/root/roboticsAutoAttendance/roboticsAutoAttendance.db")
dbc = db.cursor()
# SQLite Tables:
# LOGINS/LOGOUTS/ALLTAPS: timestamp TEXT, id INT, classification TEXT {"unclassified, login, logout"), username TEXT
# USERS: id INT, username TEXT

# init Google Sheets API
sheet = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name("creds.json")).open_by_key(
    '16QkxLrEpXwNaN1Y1BnShhLx6VxFvj_4cfdWxqE5kBMY')
hoursdata = sheet.worksheet("Hours Data")
newusers = sheet.worksheet("New Users")
reg = sheet.worksheet("Registration")

# init PN532
pn532_agent = subprocess.Popen(["echo"])  # create dummy agent

# init display
disp = ST7735.ST7735(
    port=0,
    cs=0,  # BG_SPI_CSB_BACK or BG_SPI_CS_FRONT
    dc=26,
    backlight=16,
    rotation=0,
    width=128,
    height=160,
    rst=18,
    spi_speed_hz=4000000
)
WIDTH = disp.width
HEIGHT = disp.height

fonttiny = ImageFont.truetype(font_filepath, 8)
fontsmall = ImageFont.truetype(font_filepath, 12)
fontmed = ImageFont.truetype(font_filepath, 15)
fontlarge = ImageFont.truetype(font_filepath, 22)

disp.begin()

# init GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(buzzer_pin, GPIO.OUT)


# functions for PN532
def reset_agent(agent): # reset PN532 subprocess
    agent = subprocess.Popen(["sh", "/root/roboticsAutoAttendance/SASCard-read.sh"], stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT)
    return agent


def get_output(agent): # communicate with PN532
    stdout, stderr = agent.communicate()
    if stderr:
        print("An error occurred during subprocess")
        print(stderr)
    return stdout


# functions for SQLite and Google Sheets
def convertDateTime(sqldatetime):  # returns seconds since Aug 1, 2020
    t = time.strptime(sqldatetime, "%Y-%m-%d %H:%M:%S")
    return time.mktime(t) - 1596240000  # Time between Aug 1, 2020 and Jan 1, 1970


def convertUnixTime(unixtime): # returns seconds since Aug 1, 2020
    return unixtime - 1596240000


def classify(new, prev, prevtype):  # classifies entry using time since previous entry, returns either unclassified, login, or an int (add to hours)
    if prevtype == "login":
        if prev == None:
            return "login"
        dist = new - prev
        print("previous login was ",dist)
        if dist < 0:
            return "you can't do that"
        elif dist < 15:
            return "unclassified"
        elif dist > 36000:
            return "login"
        else:
            return dist
    elif prevtype == "logout":
        return "login"
    return


def isInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False

def loghoursdata(identifier, snds, username):
    datestring = time.strftime("%Y-%m-%d", time.localtime())
    timestring = time.strftime("%H:%M:%S", time.localtime())
    hrs = snds / 3600 
    prevtime = time.localtime(time.mktime(time.localtime()) - snds)
    startdatestring = time.strftime("%Y-%m-%d", prevtime)
    endtimestring = time.strftime("%H:%M:%S", prevtime)
    a = [datestring, timestring, username, hrs, snds, startdatestring, endtimestring]
    a = [str(b) for b in a]
    hoursdata.append_row(a)
    print("Logged", hrs, "hours for user", username)

def lognewuser(identifier):
    datestring = time.strftime("%Y-%m-%d", time.localtime())
    timestring = time.strftime("%H:%M:%S", time.localtime())
    b32 = base64.b32encode(str(identifier).encode('utf-8')).decode('utf-8')
    a = [datestring, timestring, identifier, b32]
    newusers.append_row(a)
    print("Logged new user", identifier, "with RID", b32)

def logtosqlite(identifier, classification, username=None): # main function for sqlite logging
    logout = False
    if isInt(classification) and username:
        logout = True
        loghoursdata(identifier, classification, username)
        classification = "logout"
    if username:
        print('has username')
        dbc.execute(
            "INSERT INTO ALLTAPS (timestamp, id, classification, username) VALUES(datetime('now', 'localtime')," + str(
                identifier) + ",\"" + classification + "\",\"" + username + "\")")
        if classification == "login":
            dbc.execute(
                "INSERT INTO LOGINS (timestamp, id, classification, username) VALUES(datetime('now', 'localtime')," + str(
                    identifier) + ",\"" + classification + "\",\"" + username + "\")")
            print("login")
        elif logout:
            dbc.execute(
                "INSERT INTO LOGOUTS (timestamp, id, classification, username) VALUES(datetime('now', 'localtime')," + str(
                    identifier) + ",\"" + classification + "\",\"" + username + "\")")
            print("logout")
    else:
        dbc.execute("INSERT INTO ALLTAPS (timestamp, id, classification) VALUES(datetime('now', 'localtime')," + str(
            identifier) + ",\"" + "unclassified" + "\")")
        # print("no username")
    db.commit()
    dbc.fetchall()
    return classification


def getprevinstance(identifier):  # returns seconds since aug1,2020
    dbc.execute("SELECT timestamp FROM (SELECT * FROM ALLTAPS WHERE id=" + str(
        identifier) + " AND (classification=\"login\" OR classification=\"logout\")) ORDER BY timestamp DESC LIMIT 1")
    res = dbc.fetchone()
    # print("prev instance:", res)
    if res:
        return convertDateTime(res[0])
    return res

def getprevinstancetype(identifier):  # returns seconds since aug1,2020
    dbc.execute("SELECT classification FROM (SELECT * FROM ALLTAPS WHERE id=" + str(
        identifier) + " AND (classification=\"login\" OR classification=\"logout\")) ORDER BY timestamp DESC LIMIT 1")
    res = dbc.fetchone()
    # print("prev instance type:", res)
    if res:
        return res[0]
    return res

def getusername(identifier): # returns username if applicable, else None
    dbc.execute("SELECT username FROM USERS WHERE id=" + str(identifier))
    res = dbc.fetchone()
    if res:
        return res[0]
    else:
        return res

# buzzer thread
def buzzin():
    for x in range(2):
        GPIO.output(buzzer_pin, 1)
        time.sleep(0.1)
        GPIO.output(buzzer_pin, 0)
        time.sleep(0.1)
    time.sleep(1.6)

def buzzout():
    GPIO.output(buzzer_pin, 1)
    time.sleep(0.18)
    GPIO.output(buzzer_pin, 0)
    time.sleep(1.82)

def buzznew():
    for x in range(3):
        GPIO.output(buzzer_pin, 1)
        time.sleep(0.07)
        GPIO.output(buzzer_pin, 0)
        time.sleep(0.07)
    time.sleep(1.58)

# display functions
def referencerotate(image):
    return image.rotate(imgrotation * 90, expand=True)

def defaultdisplay():
    img = Image.open(bg_filepath)
    img.resize((160, 128))
    if ipenable:
        draw = ImageDraw.Draw(img)
        draw.text((2, 2), "IP:"+str(netifaces.ifaddresses(networkinterface)[2][0]['addr']), (0,0,0), font=fonttiny)
    img = referencerotate(img)
    disp.display(img)

def display(msg, filepath, fnt=fontmed):
    img = Image.open(bg_filepath)
    img.resize((160, 128))
    img2 = Image.open(filepath)
    img2.resize((160, 128))
    img.paste(img2, (0,0), mask=img2)
    draw = ImageDraw.Draw(img)
    w, h = draw.textsize(msg, font=fnt)
    draw.multiline_text((80-w/2, 96), msg, (0,0,0), font=fnt)
    img = referencerotate(img)
    disp.display(img)

def logindisplay(user):
    display("Welcome, "+user+"!", checkmark_filepath)
    
def logoutdisplay(user):
    display("Bye, "+user+"!", exit_filepath)

def invaliddisplay():
    display("Please wait...", dots_filepath)

def newuserdisplay(idf):
    display("Registration ID: \n"+base64.b32encode(str(idf).encode('utf-8')).decode('utf-8'), user_filepath, fnt=fontsmall)

def processingdisplay():
    display("Processing...", wheel_filepath)

def newuserfaildisplay():
    display("Registration Failed.", newuserfail_filepath)

def newuserregdisplay(b32):
    display("Successfully registered.\nTap again to sign in.", newuserreg_filepath, fnt=fontsmall)
    
# new user registration
def checkiftagpresent(b32):
    regs = reg.col_values(2)
    print(regs, b32)
    index = -1
    for i in range(len(regs)):
        if regs[i] == b32:
            index = i
    if index == -1:
        return False
    else:
        username = reg.cell(index+1, 3).value
        return username

def registernewuser(identifier, username): # logs to SQLite
    print("INSERT INTO USERS (id, username) VALUES("+str(identifier)+", \""+str(username)+"\")")
    dbc.execute("INSERT INTO USERS (id, username) VALUES("+str(identifier)+", \""+str(username)+"\")")
    db.commit()

def register(identifier):
    b32 = base64.b32encode(str(identifier).encode('utf-8')).decode('utf-8')
    un = checkiftagpresent(b32)
    print("tag presence:", un)
    if un:
        registernewuser(identifier, un)
        # successfully registered
        newuserregdisplay(b32)
        print("registered new user")
        return 0.5
    else:
        # not success :((((((
        lognewuser(identifier)
        newuserdisplay(identifier)
        print("not registered.")
        return 8
        
# loop program
while True:
    # set up for pn532
    pn532_agent = reset_agent(pn532_agent)
    defaultdisplay()
    print("waiting for SASCard....")
    output = get_output(pn532_agent)
    # print(output) # debug
    output = output.decode('utf-8').replace("\n", "").replace("Rx: RF Transmission Error", "").split(
        " ")  # format everything
    while '' in output:  # remove empty '' that .split(" ") likes to create for some reason
        output.remove('')
    output = [int(i, 16) for i in output[1:]]  # int-ify
    identifier = output[3] << 24 | output[4] << 16 | output[5] << 8 | output[6]  # create identifier in int
    protocol = output[7] << 24 | output[8] << 16 | output[9] << 8 | output[10]  # create protocol in int
    info = output[11:15]
    # print(identifier, protocol, info) # debug
    if protocol != 0:
        print("Invalid protocol! Not continuing")
        # display invalid card, wait 2 seconds
        continue
    print("Card detected: \nUnique Identifier:", identifier, "\nProtocol:", protocol, "\nInfo:", info)
    processingdisplay()
    username = getusername(identifier)
    if username:
        print("Welcome,", username.split(" ")[0] + "!")
    else:
        print("New User Detected!")
    action = logtosqlite(identifier, classify(convertUnixTime(int(time.time())), getprevinstance(identifier), getprevinstancetype(identifier)),
                getusername(identifier))
    if username and action == "login": # case login
        print("logging in")
        buzzerthread = threading.Thread(target=buzzin)
        buzzerthread.start()
        logindisplay(username.split(" ")[0])
        buzzerthread.join()
    elif username and action == "logout": # case logout
        print("logging out")
        buzzerthread = threading.Thread(target=buzzout)
        buzzerthread.start()
        logoutdisplay(username.split(" ")[0])
        buzzerthread.join()
    elif username: # case nolog
        invaliddisplay()
        time.sleep(2)
    else: # case notloggedin
        print("new user detected (else)")
        buzzerthread = threading.Thread(target=buzznew)
        buzzerthread.start()
        q = register(identifier)
        buzzerthread.join()
        time.sleep(q) # 2s already, 2.5s total if registered, 10s total if not (to allow user to jot down RID)
    print("Scan complete.\n\n\n")
