# Home automation telegram bot
Home automation project written in Python using Telegram's python bot API wrapper (python-telegram-bot).  
Interacts with Xiaomi devices (python-miio library) and Phillips Hue devices (phue)

### How it works

- Bot is hosted in a local machine (Xiaomi devices do not support remote/internet control. Philips Hue devices do, but adds lag). In my case, I have it running 24/7 in a Raspberry Pi 3 Model B.
- Bot receives, processes and executes commands through Telegram (Telegram bot). First requirement is creating a new bot in telegram and getting its token.

### Features

- Support for *Xiaomi* devices. In this specific case, for the *Mi Robot Vacuum V1*:
  - Clean a room (House coordinates are mapped)
  - Go to a room, without cleaning it.
  - Pause and resume.
  - Change the fan speed (power)
  - Return to the charging station.
- Support for *Philips Hue* devices (Light bulbs, sensors...):
  - Presence sensor routine: Turn corridor light on when presence is detected (also bathroom's one at early morning). Off when not. Color of the light is different depending of the sun state. Warmer in the night, colder in the morning.
  - Turn lights on/off
  - Get luminance and temperature from sensor
  - Modify light parameters: Brightness, saturation, hue, color (given HEX value), random color, colorloop mode...
- Some extras, like getting solar information in my location (Credits to https://sunrise-sunset.org, nice API!)
