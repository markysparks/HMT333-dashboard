#!/bin/bash

# Set the initial backlight brightness from the environment variable
echo -n "$BRIGHTNESS" > /sys/class/backlight/rpi_backlight/brightness

# Disable WiFi power saving, stops WiFi going to sleep after a long period of inactivity
iw wlan0 set power_save off

if [ ! -z ${ENABLE_BACKLIGHT_TIMER+x} ] && [ "$ENABLE_BACKLIGHT_TIMER" -eq "1" ]
then
  (crontab -l; echo "${BACKLIGHT_ON:-0 8 * * *} /usr/src/backlight_on.sh") | crontab -
  (crontab -l; echo "${BACKLIGHT_OFF:-0 23 * * *} /usr/src/backlight_off.sh") | crontab -
fi

crond -f
