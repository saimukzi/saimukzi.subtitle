import hashlib
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

    def run(self):
        try:
            self.running = True

            self.start_web_server()
            self.audio_listener = audio_listener.AudioListener(self)
            self.translation_agent = translation_agent.TranslationAgent(self)

            self.translation_agent.start()
            self.audio_listener.start()

            self.wait()
        except:
            raise
        finally:
            self.running = False

            if self.audio_listener is not None:
                self.audio_listener.stop()
            if self.translation_agent is not None:
                self.translation_agent.stop()
            self.stop_web_server()

        # self.stop_speech_to_text()

    def start_web_server(self):
        self.web_server = web_server.WebServer(self)
        self.web_server.start()

    def stop_web_server(self):
        self.web_server.stop()

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
            self.main_lock.notify()


def run(init_args):
    runtime = Runtime(init_args)
    runtime.run()
