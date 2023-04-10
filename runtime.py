import hashlib
import json
# import stt
import audio_listener
import threading
import translation_agent
import web_server

class Runtime:

    def __init__(self, init_args):
        self.init_args = init_args

        self.running = False
        self.text = ''
        self.text_md5 = hashlib.md5(self.text.encode('utf-8')).hexdigest()
        self.main_lock = threading.Condition()
        self.status = {}
        self.status_hash = hashlib.md5(json.dumps(self.status).encode('utf-8')).hexdigest()
        self.audio_input_device_hash = ''

        self.audio_listener = None
        self.translation_agent = None

        self.update_status('operation','OFF')

    def run(self):
        try:
            self.running = True

            self.load_audio_input_device_hash()

            self.start_web_server()

            self.wait()
        except:
            raise
        finally:
            self.running = False

            self.disable()
            self.stop_web_server()

        # self.stop_speech_to_text()

    def start_web_server(self):
        self.web_server = web_server.WebServer(self)
        self.web_server.start()

    def stop_web_server(self):
        self.web_server.stop()

    def enable(self):
        self.update_status('operation','> ON')
        with self.main_lock:
            if self.audio_listener is None:
                self.audio_listener = audio_listener.AudioListener(self)
            if self.translation_agent is None:
                self.translation_agent = translation_agent.TranslationAgent(self)

            self.translation_agent.start()
            self.audio_listener.start()
        self.update_status('operation','ON')

    def disable(self):
        self.update_status('operation','> OFF')
        with self.main_lock:
            if self.audio_listener is not None:
                self.audio_listener.stop()
                self.audio_listener = None
            if self.translation_agent is not None:
                self.translation_agent.stop()
                self.translation_agent = None
        self.update_status('operation','OFF')

    def set_audio_input_device_hash(self, audio_input_device_hash):
        with self.main_lock:
            self.audio_input_device_hash = audio_input_device_hash
            self.update_status('audio_input_device_hash', audio_input_device_hash)

    # def start_audio_listener(self):
    #     self.audio_listener = audio_listener.AudioListener(self)
    #     self.audio_listener.start()

    # def start_speech_to_text(self):
    #     self.speech_to_text = stt.SpeechToText(self)
    #     self.speech_to_text.start()

    # def stop_speech_to_text(self):
    #     self.speech_to_text.stop()

    # def start_translation_agent(self):
    #     self.translation_agent = translation_agent.TranslationAgent(self)
    #     self.translation_agent.start()

    def wait(self):
        try:
            with self.main_lock:
                while self.running:
                    # print('Waiting...')
                    self.main_lock.wait(timeout=1)
        except KeyboardInterrupt:
            pass
            # print('Keyboard interrupt')
            # self.running = False

    def update_text(self, text):
        with self.main_lock:
            self.text = text
            self.text_md5 = hashlib.md5(self.text.encode('utf-8')).hexdigest()
            self.update_status('subtitle', text)
            self.main_lock.notify()

    def update_status(self, key, value):
        with self.main_lock:
            self.status[key] = value
            status_json = json.dumps(self.status)
            self.status_hash = hashlib.md5(status_json.encode('utf-8')).hexdigest()
            self.main_lock.notify()

    def load_audio_input_device_hash(self):
        if self.init_args.device is None:
            return
        init_device = self.init_args.device
        audio_input_device_list = audio_listener.get_audio_input_device_list()
        audio_input_device_list = filter(lambda info: init_device in info['name'], audio_input_device_list)
        audio_input_device_list = list(audio_input_device_list)
        if len(audio_input_device_list) == 0:
            print('No audio input device found')
            return
        print(audio_input_device_list[0])
        self.set_audio_input_device_hash(audio_input_device_list[0]['hash'])


def run(init_args):
    runtime = Runtime(init_args)
    runtime.run()
