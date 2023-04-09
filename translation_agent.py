from collections import deque
import threading
import traceback
import pyaudio
from six.moves import queue
from google.cloud import speech
import time
import numpy as np

RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

class TranslationAgent:

    def __init__(self, runtime):
        self.runtime = runtime
        self.init_args = runtime.init_args
        self.main_lock = runtime.main_lock

        # self.audio_buffer = queue.Queue()
        self.audio_buffer = None
        self.preactive_buffer = deque()

        self.enabled = False
        # self.state = None
        # self.state_time = None

        self.thread = None
        self.thread_lock = threading.Condition()

    def start(self):
        with self.thread_lock:
            if self.thread is not None:
                return
            self.thread = threading.Thread(target=self.run)
            self.thread.start()

    def stop(self):
        with self.thread_lock:
            if self.thread is None:
                return
            self.thread.join()
            self.thread = None

    def run(self):
        try:
            with self.main_lock:
                self.audio_buffer = queue.Queue()

            client = speech.SpeechClient()
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=RATE,
                language_code=self.init_args.language_code,
            )

            streaming_config = speech.StreamingRecognitionConfig(
                config=config, interim_results=True
            )

            while self.runtime.running:
                print('Listening...')

                audio_generator = self.audio_generator()

                if not self.runtime.running:
                    break

                print('Processing...')

                requests = (
                    speech.StreamingRecognizeRequest(audio_content=content)
                    for content in audio_generator
                )

                responses = client.streaming_recognize(streaming_config, requests)

                for response in responses:

                    if not self.runtime.running:
                        break

                    if not response.results:
                        continue

                    result = response.results[0]
                    if not result.alternatives:
                        continue

                    transcript = result.alternatives[0].transcript

                    print(transcript)

                    self.runtime.update_text(transcript)

                    # with self.main_lock:
                    #     if result.is_final:
                    #         self.state = 'FINISHED'
                    #         self.state_time = time.time()
                    #     elif self.state == 'PROCESS_EMPTY' and len(transcript) > 0:
                    #         self.state = 'PROCESS_BUSY'
                    #         self.state_time = time.time()

                print('Finished listening')

            print('SpeechToText thread finished')
        except:
            traceback.print_exc()
            with self.main_lock:
                self.runtime.running = False
                self.runtime.main_lock.notify()
        finally:
            with self.main_lock:
                self.audio_buffer = None

    def on_audio_listener_data(self, in_data):
        with self.main_lock:
            audio_buffer = self.audio_buffer
        if audio_buffer is None: return
        audio_buffer.put(in_data)

    def on_audio_listener_stopped(self):
        with self.main_lock:
            audio_buffer = self.audio_buffer
        if audio_buffer is None: return
        audio_buffer.put(None)


    def audio_generator(self):
        ret = self._audio_buffer_generator()
        ret = self._push_preactive_buffer(ret)
        ret = self._noise_filter_generator(ret)
        ret = self._wait_generator(ret)
        ret = self._join_data_generator(ret)
        return ret


    def _audio_buffer_generator(self):
        with self.main_lock:
            audio_buffer = self.audio_buffer
        if audio_buffer is None: return

        while self.runtime.running:
            content = audio_buffer.get()
            if content is None: break
            yield content


    def _push_preactive_buffer(self, generator):
        for content in generator:
            self.preactive_buffer.append(content)
            if len(self.preactive_buffer) > 5: # config-able
                self.preactive_buffer.popleft()
            yield content


    def _noise_filter_generator(self, generator):
        # wait noise cotent
        for c in generator:
            content = c
            content_np = np.frombuffer(content, dtype=np.int16)
            content_np = content_np.astype(np.int32)
            context_diff = content_np.max() - content_np.min()
            if context_diff >= self.init_args.speech_threshold:
                break

        if not self.runtime.running:
            return
        
        for c in self.preactive_buffer:
            yield c
        yield content

        # wait silence
        silence_buffer = deque()
        silence_count = 0
        for c in generator:
            content = c
            content_np = np.frombuffer(content, dtype=np.int16)
            content_np = content_np.astype(np.int32)
            context_diff = content_np.max() - content_np.min()
            if context_diff < self.init_args.speech_threshold:
                silence_count += 1
            else:
                silence_count = 0
            if silence_count < 5: # config-able
                while len(silence_buffer) > 0:
                    yield silence_buffer.popleft()
                yield content
            elif silence_count < 15: # config-able
                silence_buffer.append(content)
            else:
                break


    def _wait_generator(self, generator):
        have_content = False
        for c in generator:
            have_content = True
            content = c
            break
        if have_content:
            return self._append_generator(content, generator)
        else:
            return ()


    def _append_generator(self, content, generator):
        yield content
        for c in generator:
            yield c

    def _join_data_generator(self, generator):
        ret = JoinDataGenerator(generator)
        return ret


class JoinDataGenerator:

    def __init__(self, generator):
        self.generator = generator
        self.lock = threading.Condition()
        self.content_queue = deque()
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def __iter__(self):
        running = True
        while running:
            with self.lock:
                while len(self.content_queue) <= 0:
                    self.lock.wait()
                content_list = list(self.content_queue)
                self.content_queue.clear()
            if content_list[-1] is None:
                content_list = content_list[:-1]
                running = False
            ret = b''.join(content_list)
            # print(len(ret))
            yield ret

    def run(self):
        # print('JoinDataGenerator started')
        for content in self.generator:
            with self.lock:
                self.content_queue.append(content)
                self.lock.notify()
        with self.lock:
            self.content_queue.append(None)
            self.lock.notify()
        # print('JoinDataGenerator finished')

    def join(self):
        self.thread.join()
