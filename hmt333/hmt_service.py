import json
import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from hmt_ascii import HmtAscii
from datetime import datetime


class HMTservice:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        logging.captureWarnings(True)

        config_location = '/data/config.ini'
        # config_location = '../config.ini'

        serial_port = os.getenv('HMT333_PORT', '/dev/tty.usbserial-AI02FCVO')
        serial_baud = int(os.getenv('HMT333_BAUD', 115200))
        data_poll_interval = int(os.getenv('DATA_POLL_INTERVAL', 60))
        self.sensor = HmtAscii(
            serial_port, serial_baud, data_poll_interval, config_location)

    def get_data(self):
        """Return the latest recorded values from the instrument as
        captured by the data reception and decoding functions in this
        class. A timestamp and age of the reading are also provided.
        :return: JSON formatted temperature reading (degrees C),
        timestamp and age of the reading in seconds."""
        data = self.sensor.latest_data()
        if data['temperature'] is not None:
            obs_age = (datetime.utcnow() - data['time_obs']).seconds
            # logging.info(data)
            return [
                {
                    'measurement': 'HMT333',
                    'fields': {
                        'timestamp': data['timestamp'],
                        'obs_age': obs_age,
                        'temperature': data['temperature'],
                        'max_temp_calc': data['max_temp'],
                        'min_temp_calc': data['min_temp'],
                        'data_points': data['data_points']

                    }
                }
            ]

        else:
            return [
                {
                    'measurement': 'HMT333',
                    'fields': {
                        'timestamp': '',
                        'obs_age': '',
                        'temperature': '',
                        'max_temp_calc': '',
                        'min_temp_calc': '',
                        'data_points': ''
                    }
                }
            ]


class HMT333http(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        measurements = HMTservice.get_data()
        self.wfile.write(json.dumps(measurements[0]['fields']).encode('UTF-8'))


# Start the server that answers requests for readings and inputs received
# data for extraction and processing.
if os.getenv('HMT333_ENABLE', 'true') == 'true':
    HMTservice = HMTservice()

    while True:
        server_address = ('', 7575)
        httpd = HTTPServer(server_address, HMT333http)
        logging.info('HMT333 sensor HTTP server running')
        httpd.serve_forever()
