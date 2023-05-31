import logging
import os
import pickle
import time

from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler


class MaxMinTemp:
    """Max temp monitor"""
    def __init__(self):
        # Set up a record of each temperature received through the day and
        # night periods (used when determining the latest MAX
        # and MIN temperatures).
        self.maxmin_temp_data = dict(max=None, min=None, data_points=None)
        # Load the list from the file if available and less than 30 mins old
        if os.path.isfile('/usr/src/app/temps.pkl') and \
                self.file_age('/usr/src/app/temps.pkl') < 1800:
            with open('/usr/src/app/temps.pkl', 'rb') as f:
                self.temps = pickle.load(f)
                max_temp = max(self.temps)
                min_temp = min(self.temps)
                self.maxmin_temp_data.update(dict(
                    max=max_temp, min=min_temp, data_points=len(self.temps)))
                logging.info('Previous temperatures list loaded....')
        else:
            # Remove any old temps file that didn't pass the file_age check
            if os.path.isfile('/usr/src/app/temps.pkl'):
                os.remove('/usr/src/app/temps.pkl')
            logging.info('Temperatures list will be created in max_temp_calc')
            self.temps = []
            self.data_points = 0

        # Get a scheduler (APScheduler) instance and set up the daily
        # maximum/minimum temperature reset time.
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.reset_max_min_temp,
            CronTrigger(hour=9, minute=1, timezone="UTC"))
        self.scheduler.start()

    def max_temp_calc(self, temperature):
        """Update the temperature list with the provided reading and
        return the latest mx/min and number of data points
        :return: max, min temperature and number of data points in the list."""
        self.temps.append(temperature)

        # Save the state of temperatures list across reboots by saving to a
        # binary file. On initial start-up Max/Min reports should be disabled
        # until a days worth (0900-0900hrs) of data has been collected as this
        # file data may be old. This is a solution to try and keep
        # recording max/min despite reboots due to internet connection loss
        # See the internet checking in metoffice_wow.py and note the file age
        # check made before opening the file in the init section of this class.
        with open('temps.pkl', 'wb+') as f:
            pickle.dump(self.temps, f)
            logging.info('Temperatures list saved to binary file temps.pkl')
        max_temp = max(self.temps)
        min_temp = min(self.temps)
        self.maxmin_temp_data.update(dict(
                    max=max_temp, min=min_temp, data_points=len(self.temps)))
        return self.maxmin_temp_data

    @staticmethod
    def file_age(filename):
        """Determine how long since a file has been last modified"""
        mod_time = os.path.getmtime(filename)
        curr_time = time.time()
        time_diff = curr_time - mod_time
        return time_diff

    def reset_max_min_temp(self):
        """Remove any file containing temperatures and also clear
        the running list of temperatures"""
        if os.path.isfile('/usr/src/app/temps.pkl'):
            os.remove('/usr/src/app/temps.pkl')
        self.temps.clear()
