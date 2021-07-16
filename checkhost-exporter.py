import logging
import json
from prometheus_client import CollectorRegistry, Gauge, start_http_server
from urllib3 import PoolManager
import time
import os
import sys

EXPORTER_PORT = os.getenv("CHECKHOST_EXPORTER_PORT", 8100)
CHECK_DOMAIN = os.getenv("CHECKHOST_CHECK_DOMAIN")
NODES_COUNT = os.getenv("CHECKHOST_NODES_COUNT", 7)
API_REQ_RETRIES = os.getenv("API_REQ_RETRIES", 3)
DEBUG = os.getenv("CHECKHOST_EXPORTER_DEBUG", True)
http = PoolManager()
registry = CollectorRegistry()
g_metric = Gauge('request_time', f'Request time to {CHECK_DOMAIN}', ('from', 'to'), registry=registry)


class Check:
    def __init__(self, response):
        self.req_id = response['request_id']
        self.nodes_dict = {}
        for k, v in response['nodes'].items():
            self.nodes_dict[k] = {}
            _, self.nodes_dict[k]['country'], self.nodes_dict[k]['city'], _, _ = v


class HttpCheck(Check):
    def parse_check_result(self, data):
        for k, v in data.items():
            # check if node succesfully checks domain
            if v[0] and (v[0][0] == 1):
                _, self.nodes_dict[k]['response_time'], _, _, _ = v[0]
            else:
                self.nodes_dict[k]['response_time'] = 0


class PingCheck(Check):
    @staticmethod
    def calc_avg_ping_time(pings):
        return (elem[1] for elem in pings if elem[0] == 'OK')

    def parse_check_result(self, data):
        for k, v in data.items():
            self.nodes_dict[k]['ping_results'] = v[0]
            timings = (elem[1] for elem in v[0] if elem[0] == 'OK')
            self.nodes_dict[k]['avg_time'] = sum(timings)/len(v[0])


def run_check(check_type, nodes_count):
    uri = "https://check-host.net/check-{}?host=https://{}&max_nodes={}".format(check_type,
                                                                                CHECK_DOMAIN,
                                                                                nodes_count)
    api_response = api_request(uri)
    return check_result_handler(api_response, check_type)


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


def check_result_handler(res, check_type):
    try:
        opts = {
            'http': HttpCheck,
            'ping': PingCheck
        }
        check = opts[check_type](res)
        uri = "https://check-host.net/check-result/{}".format(check.req_id)
        resp = api_request(uri)
        while None in resp.values():
            logger.debug('Not complete result ("None" in values), trying one more time')
            time.sleep(3)
            resp = api_request(uri)
        check.parse_check_result(resp)
        return check
    except KeyError:
        if 'limit_exceeded' in res.values():
            logger.error('Checkhost API limiting requests, waiting for 5min')
            time.sleep(600)


def gen_metric(check: HttpCheck):
    for node in check.nodes_dict:
        rounded_time = round(check.nodes_dict[node]["response_time"], 3)
        g_metric.labels(check.nodes_dict[node]["country"], CHECK_DOMAIN).set(rounded_time)


def set_logger(name):
    lg = logging.getLogger(name)
    lg.setLevel(logging.DEBUG) if DEBUG else lg.setLevel(logging.WARNING)
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s]: %(message)s')
    handler.setFormatter(formatter)
    lg.addHandler(handler)
    return lg


if __name__ == "__main__":
    logger = set_logger('checkhost-exporter')
    if not CHECK_DOMAIN:
        logger.error('CHECKHOST_CHECK_DOMAIN environment variable is empty. Cannot continue.')
        exit(1)
    start_http_server(EXPORTER_PORT, registry=registry)
    while True:
        gen_metric(run_check('http', NODES_COUNT))
        time.sleep(30)


