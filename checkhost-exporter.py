from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler
import logging
import json
from urllib3 import PoolManager
import time
import os

EXPORTER_PORT = os.getenv("CHECKHOST_EXPORTER_PORT", 8100)
CHECK_DOMAIN = os.getenv("CHECKHOST_CHECK_DOMAIN")
NODES_COUNT = os.getenv("CHECKHOST_NODES_COUNT", 3)
DEBUG = os.getenv("CHECKHOST_EXPORTER_DEBUG", True)
http = PoolManager()


class ExporterHTTPRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/metrics":
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(generate_response('http', NODES_COUNT).encode('utf-8'))
        elif self.path == "/":
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            html = """
                   <html>
                   <head><title>CheckHost Exporter</title></head>
                   <body>
                   <h2>Checkhost Exporter v0.1</h2>
                   <p>Use <a href="/metrics">/metrics</a> url to get metrics</p>
                   </body>
                   </html>
            """
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_error(404, "Not found", "Use metrics url")

    def log_message(self, format, *args):
        logger.info("Send metrics")


class HTTPCheck:
    def __init__(self, response):
       #     for item in json_to_obj['nodes']:
       #         setattr(self, item, json_to_obj['nodes'][item])
        self.nodes = response['nodes']
        self.req_id = response['request_id']
#        for k, v in response['nodes']:
#            setattr(self, k, {})
#            for val in v:
#                setattr()


def initialize():
    pass

def generate_response(check_type, nodes_count):
    uri = "https://check-host.net/check-{}?host=https://{}&max_nodes={}".format(check_type, CHECK_DOMAIN, nodes_count)
    api_response = api_request(uri)
    opts = {
            'http': http_check_resp_parse,
            'ping': ping_check_resp_parse
    }
    check_result = opts[check_type](api_response)
    return check_result


def api_request(uri):
    logger.debug('Request to API: {}'.format(uri))
    response = http.request('GET', uri, headers={"Accept": "application/json"})
    logger.debug('Raw response from API: {}'.format(response.data))
    result = json.loads(response.data.decode())
    logger.debug('Parsed response from API: {}'.format(result))
    if None in result.values():
        logger.debug('Not complete result ("None" in values), trying one more time')
        time.sleep(1)
        result = api_request(uri)
    return result


def http_check_resp_parse(res):
    def format_message(data_dict):
        msg = ""
        for node in data_dict:
 #           for param in data_dict[node].keys():
             msg += "response_time{{country=\"{}\", site=\"{}\"}} {}\n".format(data_dict[node]["country"], CHECK_DOMAIN, data_dict[node]["response_time"])
        return msg
    check = HTTPCheck(res)
    uri = "https://check-host.net/check-result/{}".format(check.req_id)
    get_resp = api_request(uri)
    result = {}
    for node in check.nodes:
        if get_resp[node]:
            result[node] = {}
            result[node]['country_code'] = check.nodes[node][0]
            result[node]['country'] = check.nodes[node][1]
            result[node]['city'] = check.nodes[node][2]
            result[node]['checker_ip'] = check.nodes[node][3]
            result[node]['response_time'] = round(get_resp[node][0][1], 3)

    return format_message(result)


def set_logger(name):
    lg = logging.getLogger(name)
    lg.setLevel(logging.DEBUG) if DEBUG else lg.setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    lg.addHandler(handler)
    return lg


def ping_check_resp_parse():
    pass


def run_server(port):
    server = HTTPServer(('', port), ExporterHTTPRequestHandler)
    server.serve_forever()




if __name__ == "__main__":
    logger = set_logger('checkhost-exporter')
    initialize()
    run_server(EXPORTER_PORT)

