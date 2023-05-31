import configparser
import logging


class ConfigHandler:
    """HMT calibration and configuration file handler. Can create a default
    configuration file if required as well as reading sensor calibration
    coefficients for applying to raw temperature readings. The configuration
    file is /data/config.ini on an operational device running Balena OS and
    can be accessed by other container services. For easier testing, provision
    is made for also storing the file in the top level project directory"""

    def __init__(self, config_location):
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        logging.captureWarnings(True)

        self.config_location = config_location

        # Initialise HMT sensor calibration coefficients
        self.corr_M30 = 0.0
        self.corr_M20 = 0.0
        self.corr_M10 = 0.0
        self.corr_0 = 0.0
        self.corr_10 = 0.0
        self.corr_20 = 0.0
        self.corr_30 = 0.0
        self.corr_40 = 0.0
        self.corr_50 = 0.0

    def set_calibration_coefficients(self):
        """
        Use the Python 'configparser' to read in instrument calibration
        coefficients for temperatures -30/-20/-10/0/10/20/30/40/50
        deg C from the config.ini file (if available). If the config file
        is not available then fallback values of 0.0 are use.
        """
        try:
            config_object = configparser.ConfigParser()
            config_object.read(self.config_location)
            calibration = config_object['CALIBRATION']

            self.corr_M30 = calibration.getfloat('corr_M30', fallback=0.0)
            self.corr_M20 = calibration.getfloat('corr_M20', fallback=0.0)
            self.corr_M10 = calibration.getfloat('corr_M10', fallback=0.0)
            self.corr_0 = calibration.getfloat('corr_0', fallback=0.0)
            self.corr_10 = calibration.getfloat('corr_10', fallback=0.0)
            self.corr_20 = calibration.getfloat('corr_20', fallback=0.0)
            self.corr_30 = calibration.getfloat('corr_30', fallback=0.0)
            self.corr_40 = calibration.getfloat('corr_40', fallback=0.0)
            self.corr_50 = calibration.getfloat('corr_50', fallback=0.0)
            logging.info('Calibration loaded from config file....')

        except (IOError, KeyError, ValueError):
            # new config file.
            logging.info('IOError, KeyError or ValueError trying to open '
                         'and parse config file '
                         '- creating a default config file')
            self.create_config(self.config_location)

        # except FileNotFoundError:
        #     # Try loading a config file from the top level directory, rather
        #     # than the specified location.
        #     self.config_location = '../config.ini'
        #     self.set_calibration_coefficients()

    def apply_calibration(self, temp):
        """
        Apply the correct instrument calibration adjustment to the
        as read temperature. Calibration coefficients are provided for on the
        instrument calibration certificate for temperatures of -30/-20/-10/0
        /10/20/30/40/50 deg C.
        :param temp: The 'as read' temperature in degrees C from the HMT333
        :return: The 'as read' temperature plus the most appropriate
        instrument calibration coefficient (degrees C).
        """
        self.set_calibration_coefficients()

        if temp >= 45:
            temp = temp + self.corr_50
        elif temp >= 35:
            temp = temp + self.corr_40
        elif temp >= 25:
            temp = temp + self.corr_30
        elif temp >= 15:
            temp = temp + self.corr_20
        elif temp >= 5:
            temp = temp + self.corr_10
        elif temp >= -5:
            temp = temp + self.corr_0
        elif temp >= -15:
            temp = temp + self.corr_M10
        elif temp >= -25:
            temp = temp + self.corr_M20
        else:
            temp = temp + self.corr_M30
        return temp

    @staticmethod
    def create_config(config_location):
        # Get the configparser object
        config_object = configparser.ConfigParser()

        # Assume we need 2 sections in the config file, let's call them WOW
        # and CALIBRATION auth_code though not a password, is slightly
        # sensitive so is converted to a bse64 string to avoid storing this
        # in plain text in the config.ini file.
        config_object["WOW"] = {
            "site_id": '',
            "auth_code": '',
            "wow_enable": 'false',
        }
        config_object["CALIBRATION"] = {
            "serial_no": 'E123456',
            "calibration_date": '2000/01/01',
            "corr_M30": '0.0',
            "corr_M20": '0.0',
            "corr_M10": '0.0',
            "corr_0": '0.0',
            "corr_10": '0.0',
            "corr_20": '0.0',
            "corr_30": '0.0',
            "corr_40": '0.0',
            "corr_50": '0.0',
        }

        # Write the above sections to config.ini file
        try:
            with open(config_location, 'w') as conf:
                config_object.write(conf)
            logging.info('Calibration config file created....')
        except FileNotFoundError:
            logging.info('Unable to create config file in specified location')
