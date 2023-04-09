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
        parsed_path = urlparse(self.path)
        print(parsed_path)
        if parsed_path.path == '/text':
            parsed_query = parse_qs(parsed_path.query)
            if 'last_text_md5' in parsed_query:
                last_text_md5 = parsed_query['last_text_md5'][0]
                with self.server.smz_web_server.main_lock:
                    if last_text_md5 == self.server.smz_web_server.runtime.text_md5:
                        self.server.smz_web_server.main_lock.wait(timeout=1)
            self.send_response(200)
            self.send_header('Content-type', 'text/json')
            self.end_headers()
            text = self.server.smz_web_server.runtime.text
            text_md5 = self.server.smz_web_server.runtime.text_md5
            data = {'text': text, 'text_md5': text_md5}
            self.wfile.write(bytes(json.dumps(data), "utf-8"))
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
