import configparser
import os
import base64
import logging
import warnings
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, send_file

"""A small Flask web application that provides a settings web page. Settings 
for various MetOffice WoW parameters (site ID, passcode enable/disable) along
with HMT sensor calibration coefficients, serial number and calibration date.
Settings are retrieved and stored in a config.ini file. On Balena OS ths is
located at /data/config.ini and is accessible to other container service.
For testing purposes the config file can also be located in the top level 
directory of the HMT_dashboard-2 project."""

# Set up logging
logging.basicConfig(level=logging.INFO)
logging.captureWarnings(True)
logging.info('Setting up Configuration Flask Web App....')

# Dashboard home page site parameters
location_name = os.getenv('LOCATION_NAME', '')
location_id = os.getenv('LOCATION_ID', '')
sensor_name = os.getenv('SENSOR_NAME', '')

config_location = '/data/config.ini'
# config_location = '../config.ini'

# These values are used to determine if recalibrate warnings (Red date
# box colour) should be displayed in the settings and dashboard web pages.
calibration_date = ' '
recalibrate = 'false'

app = Flask(__name__)

app.config.from_object(__name__)
app.config['SECRET_KEY'] = '7d441f27d441f27567d441f2b6176a'


@app.route('/', methods=['POST', 'GET'])
def get_settings():
    """
    Return the HMT333 settings page. If the form is a POST then save the
    settings the /data/config.ini file using the Python 'configparser'.
    If a GET request is being made, load the settings from the config.ini
    file and return a populated settings page. if a settings file is not
    present then default values are used to initially populate the page.

    :return: HMT333 dashboard settings web page template, either populated
    with default settings, settings from a config file or new settings that
    have been entered into the form fields before a POST to save the
    settings.
    """
    global calibration_date
    global recalibrate
    global config_location

    if request.method == 'POST':
        site_id = request.form.get('site_id')
        auth_code = request.form.get('auth_code')
        serial_no = request.form.get('serial_no')
        calibration_date = request.form.get('calibration_date')
        corr_M30 = request.form.get('corr_M30')
        corr_M20 = request.form.get('corr_M20')
        corr_M10 = request.form.get('corr_M10')
        corr_0 = request.form.get('corr_0')
        corr_10 = request.form.get('corr_10')
        corr_20 = request.form.get('corr_20')
        corr_30 = request.form.get('corr_30')
        corr_40 = request.form.get('corr_40')
        corr_50 = request.form.get('corr_50')

        if request.form.get('wow_enable'):
            wow_enable = 'true'
        else:
            wow_enable = 'false'

        # Ascertain if the instrument is out of calibration
        recalibrate = check_recalibration(calibration_date)

        # Get the configparser object
        config_object = configparser.ConfigParser()

        # We need 2 sections in the config file, let's call them WOW
        # and CALIBRATION. "auth_code" though not a password, is slightly
        # sensitive so is converted to a bse64 string to avoid storing this
        # in plain text in the config.ini file.
        config_object["WOW"] = {
            "site_id": site_id,
            "auth_code": encode64(auth_code),
            "wow_enable": wow_enable,
        }
        config_object["CALIBRATION"] = {
            "serial_no": serial_no,
            "calibration_date": calibration_date,
            "corr_M30": corr_M30,
            "corr_M20": corr_M20,
            "corr_M10": corr_M10,
            "corr_0": corr_0,
            "corr_10": corr_10,
            "corr_20": corr_20,
            "corr_30": corr_30,
            "corr_40": corr_40,
            "corr_50": corr_50,
        }
        message = '** Configuration applied ** '

        try:
            with open(config_location, 'w') as conf:
                config_object.write(conf)
        except FileNotFoundError:
            warnings.warn('Configuration web page - '
                          'unable to write config file')

        return render_template('settings.html', site_id=site_id,
                               auth_code=auth_code, corr_M30=corr_M30,
                               corr_M20=corr_M20, corr_M10=corr_M10,
                               corr_0=corr_0, corr_10=corr_10,
                               corr_20=corr_20, corr_30=corr_30,
                               corr_40=corr_40, corr_50=corr_50,
                               serial_no=serial_no,
                               calibration_date=calibration_date,
                               message=message,
                               wow_enable=wow_enable,
                               recalibrate=recalibrate)

    # Must be a GET request for config. Note the WoW auth_code is not stored
    # as plain text in the config file but as a base64 encoded string and
    # therefore has to be decoded before use.
    else:
        try:
            config_object = configparser.ConfigParser()
            # Specified location for config file is checked first, if the file
            # doesn't exist then the top level directory is tried.
            path = Path(config_location)
            if path.is_file():
                config_object.read(config_location)
            else:
                config_object.read('../config.ini')
            wow = config_object["WOW"]
            site_id = wow.get("site_id", '')
            auth_code = decode64(wow.get("auth_code", 'MDAwMDAw'))
            wow_enable = wow.get('wow_enable')
            message = 'To use a USB keyboard, plug in and restart the unit'

            calibration = config_object['CALIBRATION']
            serial_no = calibration.get('serial_no', 'E000000')
            calibration_date = calibration.get(
                'calibration_date', '2000/01/01')
            corr_M30 = calibration.get('corr_M30', '0.0')
            corr_M20 = calibration.get('corr_M20', '0.0')
            corr_M10 = calibration.get('corr_M10', '0.0')
            corr_0 = calibration.get('corr_0', '0.0')
            corr_10 = calibration.get('corr_10', '0.0')
            corr_20 = calibration.get('corr_20', '0.0')
            corr_30 = calibration.get('corr_30', '0.0')
            corr_40 = calibration.get('corr_40', '0.0')
            corr_50 = calibration.get('corr_50', '0.0')

            # Ascertain if the instrument is out of calibration
            recalibrate = check_recalibration(calibration_date)

            return render_template('settings.html', site_id=site_id,
                                   auth_code=auth_code, corr_M30=corr_M30,
                                   corr_M20=corr_M20, corr_M10=corr_M10,
                                   corr_0=corr_0, corr_10=corr_10,
                                   corr_20=corr_20, corr_30=corr_30,
                                   corr_40=corr_40, corr_50=corr_50,
                                   serial_no=serial_no,
                                   calibration_date=calibration_date,
                                   message=message,
                                   wow_enable=wow_enable,
                                   recalibrate=recalibrate)
        except (IOError, KeyError):
            return render_template('settings.html')


@app.errorhandler(404)
def not_found_error(error):
    """
    Return a 404 'file not found' error page template.
    param error: Flask 404 error handler
    :return: Formatted 'file not found' error web page.
    """
    return render_template('404.html', location_name=location_name,
                           location_id=location_id,
                           sensor_name=sensor_name, error=error), 404


@app.errorhandler(500)
def internal_error(error):
    """
    Return a 500 application error page should there be a problem with the
    dashboard application.
    param error: Flask 500 application error handler
    :return: Formatted internal or application error web page.
    """
    return render_template('500.html', location_name=location_name,
                           location_id=location_id,
                           sensor_name=sensor_name, error=error), 500


def check_recalibration(calib_date):
    """
    Checks if today's date after the instrument calibration due date (the
    date entered into the settings web page), in which case recalibration
    of the instrument is required.
    param calib_date: The date of the instrument calibration due as entered
    through the user interface settings web page. In the format:
    YYYY/MM/DD or YYYY-MM-DD e.g. 2020/02/25
    :return: A string value 'false' if the instrument does not require
    recalibration, 'true' if it does.
    """
    recal = 'false'
    if calib_date is not ' ':
        try:
            calibration_date_obj = datetime.strptime(
                calib_date, '%Y/%m/%d').date()
        # Account for different date separator format in config file
        except ValueError:
            calibration_date_obj = datetime.strptime(
                calib_date, '%Y-%m-%d').date()

        if datetime.utcnow().date() >= calibration_date_obj:
            recal = 'true'

    return recal


def encode64(message):
    """
    Encode an ascii string into base64
    :param message:
    :return:
    """
    message_bytes = message.encode('ascii')
    base64_bytes = base64.b64encode(message_bytes)
    base64_message = base64_bytes.decode('ascii')
    return base64_message


def decode64(base64_message):
    """
    Decode a base64 string back into ascii
    :param base64_message:
    :return:
    """
    base64_bytes = base64_message.encode('ascii')
    message_bytes = base64.b64decode(base64_bytes)
    message = message_bytes.decode('ascii')
    return message


@app.route('/download')
def download_file():
    path = '/data/max-min-temp.csv'  # Set the path to your file here
    return send_file(path, as_attachment=True)


if __name__ == "__main__":
    # The small WSGI compliant web server "waitress" is used
    # to server the configuration pages.
    from waitress import serve
    serve(app, host="0.0.0.0", port=8080)

    # Use Flask built-in web server (non-production)
    # app.run(host='0.0.0.0', port=8080)
