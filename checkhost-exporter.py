import logging
import json
from prometheus_client import CollectorRegistry, Gauge, start_http_server
from urllib3 import PoolManager
import time
import os

EXPORTER_PORT = os.getenv("CHECKHOST_EXPORTER_PORT", 8100)
CHECK_DOMAIN = os.getenv("CHECKHOST_CHECK_DOMAIN")
NODES_COUNT = os.getenv("CHECKHOST_NODES_COUNT", 3)
API_REQ_RETRIES = os.getenv("API_REQ_RETRIES", 3)
DEBUG = os.getenv("CHECKHOST_EXPORTER_DEBUG", True)
http = PoolManager()
registry = CollectorRegistry()
g_metric = Gauge('request_time', f'Time of request to {CHECK_DOMAIN}', ('from', 'to'), registry=registry)


class HTTPCheck:
    def __init__(self, response):
        self.nodes = response['nodes']
        self.req_id = response['request_id']


def generate_response(check_type, nodes_count):
    uri = "https://check-host.net/check-{}?host=https://{}&max_nodes={}".format(check_type,
                                                                                CHECK_DOMAIN,
                                                                                nodes_count)
    api_response = api_request(uri)
    opts = {
            'http': http_check_resp_parse,
            'ping': ping_check_resp_parse
    }
    check_result = opts[check_type](api_response)
    return check_result


def api_request(uri, try_num=1):
    logger.debug('Request to API (try {}): {}'.format(try_num, uri))
    response = None
    try:
        response = http.request('GET', uri, headers={"Accept": "application/json"})
    except Exception as e:
        logger.error('Caught: {}'.format(e))
    if response.status == 200:
        logger.debug('Raw response from API: {}'.format(response.data))
        result = json.loads(response.data.decode())
        logger.debug('Parsed response from API: {}'.format(result))
        if None in result.values():
            logger.debug('Not complete result ("None" in values), trying one more time')
            time.sleep(3)
            result = api_request(uri)
        return result
    else:
        # retry
        try_num += 1
        if try_num < API_REQ_RETRIES + 1:
            time.sleep(1)
            logger.error('Got {}. Retry'.format(response.status))
            api_request(uri, try_num=try_num)
        else:
            logger.error('Got {}. Give up :('.format(response.status))
            exit(1)


def http_check_resp_parse(res):
    def format_message(data_dict):
        for node in data_dict:
            g_metric.labels(data_dict[node]["country"], CHECK_DOMAIN).set(data_dict[node]["response_time"])
    try:
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
        format_message(result)
    except KeyError:
        if 'limit_exceeded' in res.values():
            logger.error('Checkhost API limiting requests, waiting for 5min')
            time.sleep(600)


def set_logger(name):
    lg = logging.getLogger(name)
    lg.setLevel(logging.DEBUG) if DEBUG else lg.setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s')
    handler.setFormatter(formatter)
    lg.addHandler(handler)
    return lg


def ping_check_resp_parse():
    pass


if __name__ == "__main__":
    logger = set_logger('checkhost-exporter')
    if not CHECK_DOMAIN:
        logger.error('CHECK_DOMAIN environment variable is empty. Cannot continue.')
        exit(1)
    start_http_server(EXPORTER_PORT, registry=registry)
    while True:
        generate_response('http', NODES_COUNT)
        time.sleep(30)


