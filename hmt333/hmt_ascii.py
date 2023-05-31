import os
import warnings
import logging
import re
import serial
from config_handler import ConfigHandler
from max_min_temp import MaxMinTemp
from threading import Timer
from datetime import datetime


class HmtAscii:
    """Vaisala HMT333 sensor ascii data retrieval and extraction class.
    Requests temperature data from the sensor which responds with an ASCII
    data serial string (which is of the format: T= 12.3 'C) received on a
    system serial port. Instrument calibration coefficients are read in from
    a configuration file and then applied to the as read (raw) value. The
    instrument must be set to output temperature in units of degrees C when
    it receives a request ('SEND' command) """

    def __init__(self, serial_port, serial_baud, poll_interval,
                 config_location):

        # Set up logging
        logging.basicConfig(level=logging.INFO)
        logging.captureWarnings(True)
        logging.info('Setting up HMT sensor data collection....')

        # How often the sensor should be polled for data
        self.poll_interval = poll_interval

        self.config_location = config_location
        self.config = ConfigHandler(self.config_location)

        self.max_temp_handler = MaxMinTemp()
        self.max_temp_diff = float(os.getenv('MAX_TEMP_DIFF', 7))

        # Set up the serial port to which the HMT sensors will be connected
        # Note the sensor is most likely connected via an RF422 radio unit
        # So the serial port settings here will be for that radio unit.
        self.serial_port = serial.Serial(
            serial_port, serial_baud, timeout=10.0)
        logging.info('Serial port: ' + str(self.serial_port))
        self.serial_port.write('echo off\r\n'.encode())
        print('echo switched off')

        # Initialise startup values for temperature data
        self.timestamp = None
        self.temperature = None
        self.time_obs = None
        self.max_temp = None
        self.min_temp = None
        self.data_points = None

        # Get calibration values and start collecting readings from the HMT
        self.config.set_calibration_coefficients()
        self.get_hmt_data()

    def get_hmt_data(self):
        """Read a line of incoming data from the assigned serial port,
        then pass the data onto a processor for extraction of the
        temperature value from this ascii data string (format: T= 12.3 'C).
        Python's 'Threading-> Timer' is used to asynchronously schedule this
        method so that it keeps attempting to read any incoming data on the
        serial line. """
        try:
            # self.serial_port.flushInput()
            self.serial_port.write('send\r\n'.encode())
            logging.info('sent SEND command to HMT requesting reading...')
            # Asynchronously schedule this function to run again after
            # the data poll interval.
            Timer(self.poll_interval, self.get_hmt_data).start()
            data_bytes = self.serial_port.readline()
            data_line = str(data_bytes)
            logging.info('RAW data: ' + data_line)
            # data_line format = "T= 12.3 'C"
            # Only process output if we have actual data in the line
            if len(data_line) > 3:
                if "send" in data_line:
                    # If 'send' appears in the data line it means that
                    # the HMT sensor has been set to echo commands. This
                    # must be switched off by the 'echo off' command.
                    logging.info('send in data line - switching ECHO off')
                    self.serial_port.write('echo off\r\n'.encode())
                elif "Echo" in data_line:
                    # 'Echo' will appear in the response data line if we have
                    # just sent the 'echo off' command (the sensor is just
                    # responding by confirming echo is now off).
                    logging.info('echo in data line - skipping')
                # Complete and legitimate data will be of the form T= 12.3 'C,
                # so we check that the data line contains T= and C before
                # processing it.
                elif "T=" and "C" and "." in data_line:
                    hmt_data = self.process_hmt_data(
                        self.data_decoder(data_line))
                    # Do a basic checks that the temperature is a sensible
                    # value before further processing.
                    if self.temperature_check(
                            hmt_data['temperature']) and \
                            self.temp_consistency_check(
                                self.temperature, hmt_data['temperature'],
                                self.max_temp_diff):
                        self.time_obs = datetime.utcnow()
                        self.temperature = hmt_data['temperature']
                        self.timestamp = hmt_data['timestamp']
                        self.max_temp = hmt_data['max_temp']
                        self.min_temp = hmt_data['min_temp']
                        self.data_points = hmt_data['data_points']
                        logging.info(
                            'Calibrated temp/Max temp/Min temp/'
                            'data points/time: '
                            + str(self.temperature) + '/'
                            + str(self.max_temp) + '/'
                            + str(self.min_temp) + '/'
                            + str(self.data_points) + '/'
                            + str(self.timestamp))
                    else:
                        warnings.warn('Temperature value fails sanity checks: '
                                      + str(hmt_data['temperature']), Warning)
                else:
                    warnings.warn('Data does not contain "T=...C" element',
                                  Warning)
            else:
                warnings.warn('No response to "send" command', Warning)
        except serial.SerialException as error:
            warnings.warn("Serial port error: " + str(error), Warning)

    def data_decoder(self, data_line):
        """Extract the temperature data from the sensor ascii data
        line. The sensor must be setup to output its data in the required
        format i.e. T= 21.1 'C.
        :param data_line: Sensors ascii output string e.g T= 21.3 'C."""
        raw_temperature = None
        data = self.find_numeric_data(data_line)
        # Check we have data available (data length should be 1 which is the
        # temperature reading) and then extract numeric values from this data.
        if len(data) == 1:
            raw_temperature = round(float(data[0]), 1)
            logging.info('Decoded Temp: ' + str(raw_temperature))
        return raw_temperature

    def process_hmt_data(self, raw_temperature):
        """Apply calibration values to the raw temperature reading, get
        a timestamp, process the current temperature max/min values.
        :return: calibrated temperature, timestamp, current max and min
        temperature and the number of temperature data points stored"""
        hmt_data = dict(temperature=None, timestamp=None, max_temp=None,
                        min_temp=None, data_points=None)
        # Apply any calibrations to the HMT temperature reading
        if raw_temperature is not None:
            temperature = self.config.apply_calibration(raw_temperature)
            timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            self.max_temp_handler.max_temp_calc(temperature)
            max_temp = self.max_temp_handler.maxmin_temp_data['max']
            min_temp = self.max_temp_handler.maxmin_temp_data['min']
            data_points = self.max_temp_handler.maxmin_temp_data['data_points']
            hmt_data.update(dict(
                temperature=temperature, timestamp=timestamp,
                max_temp=max_temp,
                min_temp=min_temp, data_points=data_points))
            return hmt_data
        else:
            return None

    def latest_data(self):
        """Returns a dictionary of the latest data :return: calibrated
        temperature, timestamp, current max and min temperature and the
        number of temperature data points stored. Provides an easy method
        for the web server script hmt_service.py to get this data"""
        data = dict(temperature=self.temperature, timestamp=self.timestamp,
                    max_temp=self.max_temp, min_temp=self.min_temp,
                    data_points=self.data_points, time_obs=self.time_obs)
        return data

    @staticmethod
    def find_numeric_data(data_line):
        """Use a regular expression search pattern to find and extract all
        digit data groups. This will include values like 1, 12.3, 2345, 0.34,
        -3.5 i.e. any number or decimal number.
        param data_line: The data line from which digit groups are to be
        extracted
        :return: A list containing the extracted digit groups."""
        data_search_exp = '[-+]? (?: (?: \d* \. \d+ ) | (?: \d+ \.? ' \
                          ') )(?:' \
                          '[Ee] [+-]? \d+ ) ?'

        find_data_exp = re.compile(data_search_exp, re.VERBOSE)
        data = find_data_exp.findall(data_line)
        return data

    @staticmethod
    def temperature_check(temp):
        """
        Simple check the temperature value falls within sane limits
        (-100 to 100 deg C) and not 'None'.
        param temp: The temperature value in degrees C.
        :return: True if the value falls with limits, False otherwise.
        """
        if -60 < temp < 60 or temp is None:
            return True
        else:
            return False

    @staticmethod
    def temp_consistency_check(previous_temp, temp, max_temp_diff):
        """Check that the difference between subsequent minute temperature
        values is sane (< X C)"""
        if previous_temp is None or temp is None:
            return True
        elif temp >= previous_temp:
            temp_diff = temp - previous_temp
        else:
            temp_diff = previous_temp - temp
        if temp_diff < max_temp_diff:
            return True
        else:
            warnings.warn('Temperature difference between subsequent readings'
                          'too large >' + str(max_temp_diff) + ' C ' +
                          str(previous_temp) + '/' + str(temp), Warning)
            return False


if __name__ == '__main__':
    HmtAscii(serial_port='/dev/tty.usbserial-AI02FCVO', serial_baud=115200,
             poll_interval=60, config_location='../config.ini')
