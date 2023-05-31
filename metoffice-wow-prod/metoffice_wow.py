import os
import time
import requests
import warnings
import logging
import configparser
import base64
import json
import csv
from datetime import datetime
from threading import Timer
from apscheduler.triggers.cron import CronTrigger
from apscheduler.schedulers.background import BackgroundScheduler


class WOWservice:
    """Transmit the latest temperature data to the Met Office WoW website
    using the API detailed here:
    https://wow.metoffice.gov.uk/support/dataformats
    A scheduler is used to determine how often observations are transmitted
    and no transmission is made if the data is considered to be 'old'.
    Temperature data is obtained from the HMT333 container HTTP service."""

    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        logging.captureWarnings(True)

        self.use_ui_wow = os.getenv('USE_UI_WOW', 'true')
        self.config_location = '/data/config.ini'
        # self.config_location = '../config.ini'
        self.wow_enable = 'false'
        self.wow_site_id = ''
        self.wow_auth_key = ''
        self.api_key = os.getenv('API_KEY', '')
        self.routine_report = os.getenv('ROUTINE_REPORT', 'true')
        self.max_min_enable = os.getenv('MAX_MIN_ENABLE', 'true')
        self.min_temp_enable = os.getenv('MIN_TEMP_ENABLE', 'true')
        self.wow_max_min_minute = int(os.getenv('WOW_MAX_MIN_MINUTE', 55))
        self.wow_max_min_hour = int(os.getenv('WOW_MAX_MIN_HOUR', 8))
        self.wow_tx_minute = int(os.getenv('WOW_TX_MINUTE', 10))
        self.data_points_req = int(os.getenv('DATA_POINTS_REQ', 1400))
        self.internet_check_intv = int(os.getenv('INTERNET_CHECK', 0))

        self.wow_url = os.getenv(
            'WOW_URL', 'https://mowowprod.azure-api.net/api/Observations')
        self.softwaretype = os.getenv('SOFTWARETYPE', 'hmtdisp1')
        self.temperature_url = os.getenv(
            'TEMPERATURE_URL', 'http://HMT333:7575')

        # Time period after which data is considered to be 'old' in seconds
        self.old_data_time = float(os.getenv('OLD_DATA_TIME', 360))

        # Either get WoW configuration data from the UI configuration page
        # or get it from the units environmental variables.
        if self.use_ui_wow == 'true':
            logging.info('Using configuration page for WoW details')
            self.wow_settings()
        else:
            logging.info('Using device environmental variables for '
                         'WoW configuration data')
            self.wow_site_id = os.getenv('SITE_ID')
            self.wow_auth_key = int(os.getenv('AUTH_CODE'))
            self.wow_enable = os.getenv('WOW_ENABLE', 'true')
        logging.info('MetOffice WOW PROD transmit: ' + self.wow_enable)

        logging.info('USE UI WOW: ' + self.use_ui_wow)
        logging.info('SITE ID: ' + self.wow_site_id)
        logging.info('AUTH KEY: ' + str(self.wow_auth_key))

        # Setup the transmission scheduler
        self.scheduler = BackgroundScheduler()

        # Setup transmission of WoW messages at X mins past each hour
        self.scheduler.add_job(self.transmit_wow_data, CronTrigger(
            minute=self.wow_tx_minute, timezone="UTC"))

        # Setup transmission of previous 24hr Max/Min temp (included with
        # the hourly temperature report) to WoW at 0900 UTC
        self.scheduler.add_job(self.transmit_wow_max_min_temp, CronTrigger(
            hour=self.wow_max_min_hour, minute=self.wow_max_min_minute,
            timezone="UTC"))

        self.scheduler.start()
        self.check_internet()

    def wow_settings(self):
        """Use Python's 'configparser' to get WoW site credentials from the
        config.ini file (if available). The authorisation code is not stored
        in plain text but as a base64 string."""
        logging.info('Getting WoW settings from Configuration....')
        try:
            config_object = configparser.ConfigParser()
            config_object.read(self.config_location)

            wow = config_object["WOW"]
            self.wow_site_id = wow.get("site_id", '')
            self.wow_auth_key = self.decode64(wow.get("auth_code", 'MDAwMDAw'))
            self.wow_enable = wow.get('wow_enable', 'false')

        except (IOError, KeyError):
            logging.info('IOError or KeyError trying to open config file')

    def transmit_wow_data(self):
        """Transmit a formatted data message to the Met Office WoW website.
        Temperature data is obtained from the HMT333 container via a request
        made to its HTTP server. Date and time is formatted as required by
        the WoW API. If the data is determined to be 'old' then no transmission
        is made."""

        # check the user interface settings (if in use) in case they've changed
        if self.use_ui_wow == 'true':
            self.wow_settings()

        logging.info('USE UI WOW: ' + self.use_ui_wow)
        logging.info('SITE ID: ' + self.wow_site_id)
        # logging.info('AUTH KEY: ' + str(self.wow_auth_key))

        obs_data = requests.get(self.temperature_url)
        tempc = obs_data.json()['temperature']
        obs_age = float(obs_data.json()['obs_age'])

        data = dict()
        wow_dtg = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")

        data["reportStartDateTime"] = wow_dtg
        data["reportEndDateTime"] = wow_dtg
        data["siteId"] = self.wow_site_id
        data["siteAuthenticationKey"] = self.wow_auth_key
        data["isPublic"] = "true"
        data["isLatestVersion"] = "true"
        data["dryBulbTemperature_Celsius"] = tempc
        data["collectionName"] = 1
        data["observationType"] = 1

        logging.info('WOW-MSG prepped:')
        data = json.dumps(data)
        logging.info(data)

        wow_url = self.wow_url
        headers = {
            'Ocp-Apim-Subscription-Key': self.api_key,
            'Content-Type': 'application/json'
        }

        if self.wow_enable == 'true' and obs_age < self.old_data_time \
                and self.routine_report == 'true':
            try:
                req = requests.post(
                    wow_url, headers=headers, data=data, timeout=20)
                logging.info('WOW-message transmitted')
                logging.info(req)
            except requests.exceptions.RequestException:
                warnings.warn('Problem/timeout posting msg to WoW URL')
        else:
            logging.info('Data fails obs age check or WoW Tx not enabled:'
                         ' Obs age: ' + str(obs_age))

    def transmit_wow_max_min_temp(self):
        """Transmit a formatted data message to the Met Office WoW website.
        Temperature data is obtained from the HMT333 container via a request
        made to its HTTP server. Date and time is formatted as required by
        the WoW API. If the data is determined to be 'old' then no transmission
        is made."""

        # check the user interface settings (if in use) in case they've changed
        if self.use_ui_wow == 'true':
            self.wow_settings()

        obs_data = requests.get(self.temperature_url)
        tempc = obs_data.json()['temperature']
        max_tempc = obs_data.json()['max_temp_calc']
        min_tempc = obs_data.json()['min_temp_calc']
        obs_age = float(obs_data.json()['obs_age'])
        data_points = int(obs_data.json()['data_points'])

        data = dict()
        wow_dtg = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S+00:00")

        data["reportStartDateTime"] = wow_dtg
        data["reportEndDateTime"] = wow_dtg
        data["siteId"] = self.wow_site_id
        data["siteAuthenticationKey"] = self.wow_auth_key
        data["isPublic"] = "true"
        data["isLatestVersion"] = "true"
        data["dryBulbTemperature_Celsius"] = tempc
        if data_points >= self.data_points_req:
            data["airTemperatureMax_Celsius"] = max_tempc
            if self.min_temp_enable == 'true':
                data["airTemperatureMin_Celsius"] = min_tempc
        data["collectionName"] = 1
        data["observationType"] = 1

        logging.info('WOW-MAX-TEMP-MSG prepped:')
        data = json.dumps(data)
        logging.info(data)

        wow_url = self.wow_url
        headers = {
            'Ocp-Apim-Subscription-Key': self.api_key,
            'Content-Type': 'application/json'
        }

        if self.wow_enable == 'true' and obs_age < self.old_data_time \
                and data_points > self.data_points_req \
                and self.max_min_enable == 'true':
            try:
                req = requests.post(
                    wow_url, headers=headers, data=data, timeout=20)
                logging.info('WOW-MAX-TEMP-message transmitted')
                logging.info(req)
                logging.info(req.text)
            except requests.exceptions.RequestException:
                warnings.warn('Problem/timeout posting max/min msg to WoW URL')
            self.record_max_min_to_file([wow_dtg, tempc, max_tempc, min_tempc])
        else:
            logging.info(
                'Conditions not met for MAX/MIN WoW message - data points: ' +
                str(data_points) + 'obs age: ' + str(obs_age) + 'WoW enabled: '
                + ' Max/Min enabled: ' + str(self.max_min_enable)
                + str(self.wow_enable))

    def check_internet(self):
        """
        Check for an internet connection - if no connection available then
        execute a device reboot. This is useful when Wi-Fi is unreliable.
        The balena supervisor provides reboot functionality within its API.
        INTERNET_CHECK environmental variable sets the time interval for this
        check in seconds. If set to zero then no checks will be made
        """
        # Schedule this command to be run at a specified interval
        if self.internet_check_intv > 0:
            Timer(self.internet_check_intv, self.check_internet).start()
            logging.info('Checking internet.....')
            url = 'https://www.google.com'
            timeout = 5
            try:
                _ = requests.get(url, timeout=timeout)
            except requests.ConnectionError:
                headers = {
                    'Content-Type': 'application/json',
                }
                params = {
                    'apikey': os.getenv('BALENA_SUPERVISOR_API_KEY', ''),
                }
                _ = requests.post(
                    os.getenv('BALENA_SUPERVISOR_ADDRESS',
                              '') + '/v1/reboot',
                    params=params,
                    headers=headers)

    def record_max_min_to_file(self, values):
        # Path to the file
        file_path = '/data/max-min-temp.csv'

        # Check if the file exists, if so write the values to it.
        if os.path.isfile(file_path):
            self.save_to_csv(values, file_path)
        else:
            # If the file doesn't exist, create it and write the header row
            # and then the values.
            columns = ['DTG', 'TEMP', 'MAX', 'MIN']
            self.save_to_csv(columns, file_path)
            self.save_to_csv(values, file_path)

    @staticmethod
    def save_to_csv(values_list, filename):
        with open(filename, 'a+', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(values_list)
        logging.info(f"Values written to {filename}!")

    @staticmethod
    def decode64(base64_message):
        """
        Decode a base64 encoded string into its ascii equivalent.
        param base64_message:
        :return: The ascii decoded equivalent of the input bas64 string.
        """
        base64_bytes = base64_message.encode('ascii')
        message_bytes = base64.b64decode(base64_bytes)
        message = message_bytes.decode('ascii')
        return message


WOWservice = WOWservice()
logging.info('MET OFFICE WOW service running')

while True:
    if not WOWservice.scheduler.running:
        WOWservice.scheduler.start()
        logging.info('MET OFFICE WOW service running')
    time.sleep(60)
