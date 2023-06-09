import base64
import copy
import audio_listener
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
import json
import os
from threading import Thread
import time
import traceback
from urllib.parse import parse_qs, urlparse

MY_DIRNAME = os.path.dirname(os.path.abspath(__file__))

class WebServer(BaseHTTPRequestHandler):

    def __init__(self, runtime):
        self.runtime = runtime
        self.init_args = runtime.init_args
        self.main_lock = runtime.main_lock

        self.html_dict = {}

    def start(self):
        self.thread = Thread(target=self.run)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.thread.join()

    def run(self):
        try:
            self.load_html_dict()

            print('Starting web server')
            self.server = ThreadingHTTPServer(('',self.init_args.port), MyRequestHandler)
            self.server.smz_web_server = self
            self.server.serve_forever()
            print('Web server stopped')
        except:
            traceback.print_exc()

    def load_html_dict(self):
        # with open('web.html', 'rb') as f:
        #     self.web_html =  f.read()
        for fn in os.listdir(MY_DIRNAME):
            if fn.endswith('.html'):
                with open(os.path.join(MY_DIRNAME, fn), 'rb') as f:
                    self.html_dict[fn[:-5]] = f.read()


class MyRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            parsed_path = urlparse(self.path)
            print(parsed_path)
            if parsed_path.path == '/text':
                parsed_query = parse_qs(parsed_path.query)
                if 'last_text_md5' in parsed_query:
                    last_text_md5 = parsed_query['last_text_md5'][0]
                    with self.server.smz_web_server.main_lock:
                        timeout = time.time() + 1
                        while True:
                            if last_text_md5 != self.server.smz_web_server.runtime.text_md5: break
                            now = time.time()
                            if now >= timeout: break
                            self.server.smz_web_server.main_lock.wait(timeout=timeout-now)
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                with self.server.smz_web_server.main_lock:
                    text = self.server.smz_web_server.runtime.text
                    text_md5 = self.server.smz_web_server.runtime.text_md5
                data = {'text': text, 'text_md5': text_md5}
                self.wfile.write(bytes(json.dumps(data), "utf-8"))
            elif parsed_path.path == '/status':
                parsed_query = parse_qs(parsed_path.query)
                if 'last_status_hash' in parsed_query:
                    last_status_hash = parsed_query['last_status_hash'][0]
                    with self.server.smz_web_server.main_lock:
                        timeout = time.time() + 1
                        while True:
                            if last_status_hash != self.server.smz_web_server.runtime.status_hash: break
                            now = time.time()
                            if now >= timeout: break
                            self.server.smz_web_server.main_lock.wait(timeout=timeout-now)
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                with self.server.smz_web_server.main_lock:
                    status = copy.deepcopy(self.server.smz_web_server.runtime.status)
                    status_hash = copy.deepcopy(self.server.smz_web_server.runtime.status_hash)
                data = {'status': status, 'status_hash': status_hash}
                self.wfile.write(bytes(json.dumps(data), "utf-8"))
            elif parsed_path.path == '/audio_input_device_list':
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                audio_input_device_list = audio_listener.get_audio_input_device_list()
                data = {'audio_input_device_list': audio_input_device_list}
                self.wfile.write(bytes(json.dumps(data), "utf-8"))
            elif parsed_path.path == '/set_audio_input_device':
                parsed_query = parse_qs(parsed_path.query)
                if not 'hash' in parsed_query:
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(bytes('Bad request', "utf-8"))
                    return
                hash = parsed_query['hash'][0]
                self.server.smz_web_server.runtime.set_audio_input_device_hash(hash)
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                self.wfile.write(bytes('{"result":"OK"}', "utf-8"))
            elif parsed_path.path == '/enable':
                self.server.smz_web_server.runtime.enable()
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                self.wfile.write(bytes('{"result":"OK"}', "utf-8"))
            elif parsed_path.path == '/disable':
                self.server.smz_web_server.runtime.disable()
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                self.wfile.write(bytes('{"result":"OK"}', "utf-8"))
            elif parsed_path.path == '/set_config_dict':
                parsed_query = parse_qs(parsed_path.query)
                if not 'config' in parsed_query:
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(bytes('Bad request', "utf-8"))
                    return
                config_dict_json_b64 = parsed_query['config'][0]
                config_dict_json = base64.b64decode(config_dict_json_b64).decode('utf-8')
                config_dict = json.loads(config_dict_json)
                print(config_dict)
                self.server.smz_web_server.runtime.set_config_dict(config_dict)
                self.send_response(200)
                self.send_header('Content-type', 'text/json')
                self.end_headers()
                self.wfile.write(bytes('{"result":"OK"}', "utf-8"))
            else:
                fn = parsed_path.path[1:]
                if fn in self.server.smz_web_server.html_dict:
                    self.send_response(200)
                    self.send_header('Content-type', 'text/html')
                    self.end_headers()
                    self.wfile.write(self.server.smz_web_server.html_dict[fn])
                else:
                    self.send_response(404)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(bytes('Not found', "utf-8"))
        except:
            traceback.print_exc()
