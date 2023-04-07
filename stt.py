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

class SpeechToText(object):

    def __init__(self, runtime):
        self.runtime = runtime
        self.init_args = runtime.init_args
        self.main_lock = runtime.main_lock
        self.stream = None
        self.state = 'IDLE'
        self.state_time = None

    def start(self):
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def stop(self):
        with self.main_lock:
            if self.stream:
                self.stream.close()
        self.thread.join()

    def run(self):
        try:
            client = speech.SpeechClient()
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
                sample_rate_hertz=RATE,
                language_code=self.init_args.language_code,
            )

            streaming_config = speech.StreamingRecognitionConfig(
                config=config, interim_results=True
            )


            with MicrophoneStream(RATE, CHUNK, self) as stream:

                self.state = 'READY'

                with self.main_lock:
                    self.stream = stream

                while True:
                    print('Listening...')

                    audio_generator = stream.generator()

                    audio_generator = wait_content(audio_generator)

                    print('Processing...')

                    requests = (
                        speech.StreamingRecognizeRequest(audio_content=content)
                        for content in audio_generator
                    )

                    with self.main_lock:
                        if not self.runtime.running:
                            break

                    responses = client.streaming_recognize(streaming_config, requests)

                    # Now, put the transcription responses to use.
                    self.listen_print_loop(responses)

                    print('Finished listening')

            with self.main_lock:
                self.stream = None

            print('SpeechToText thread finished')
        except:
            traceback.print_exc()
            with self.main_lock:
                self.stream = None
                self.runtime.running = False
                self.runtime.main_lock.notify()


    def listen_print_loop(self, responses):
        for response in responses:

            if not self.runtime.running:
                break

            # print('Got response')

            if not response.results:
                continue

            # The `results` list is consecutive. For streaming, we only care about
            # the first result being considered, since once it's `is_final`, it
            # moves on to considering the next utterance.
            result = response.results[0]
            if not result.alternatives:
                continue

            # Display the transcription of the top alternative.
            transcript = result.alternatives[0].transcript

            print(transcript)

            self.runtime.update_text(transcript)

            with self.main_lock:
                if result.is_final:
                    self.state = 'FINISHED'
                    self.state_time = time.time()
                elif self.state == 'PROCESS_EMPTY' and len(transcript) > 0:
                    self.state = 'PROCESS_BUSY'
                    self.state_time = time.time()

            # print('Waiting...')


class MicrophoneStream(object):
    """Opens a recording stream as a generator yielding the audio chunks."""

    def __init__(self, rate, chunk, stt):
        self._rate = rate
        self._chunk = chunk
        self._stt = stt

        # Create a thread-safe buffer of audio data
        self._buff = queue.Queue()

        self._ready_queue = deque()

        self.closed = True

    def __enter__(self):
        self._audio_interface = pyaudio.PyAudio()

        info = None
        for i in range(self._audio_interface.get_device_count()):
            _info = self._audio_interface.get_device_info_by_index(i)
            if _info['maxInputChannels'] <= 0: continue
            if self._stt.init_args.device not in _info['name']: continue
            try:
                if not self._audio_interface.is_format_supported(
                    rate=self._rate,
                    input_device=_info['index'],
                    input_channels=1,
                    input_format=pyaudio.paInt16,
                ):
                    continue
            except:
                continue
            if info is not None:
                if _info['defaultLowInputLatency'] < info['defaultLowInputLatency']:
                    info = _info
            else:
                info = _info
            # print(info)

        assert(info is not None)
        print(info)

        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            # The API currently only supports 1-channel (mono) audio
            # https://goo.gl/z757pE
            channels=1,
            rate=self._rate,
            input=True,
            input_device_index = info['index'],
            frames_per_buffer=self._chunk,
            # Run the audio stream asynchronously to fill the buffer object.
            # This is necessary so that the input device's buffer doesn't
            # overflow while the calling thread makes network requests, etc.
            stream_callback=self._fill_buffer,
        )

        self.closed = False

        return self

    def __exit__(self, type, value, traceback):
        # self._audio_stream.stop_stream()
        # self._audio_stream.close()
        # self.closed = True
        # # Signal the generator to terminate so that the client's
        # # streaming_recognize method will not block the process termination.
        # self._buff.put(None)
        # self._audio_interface.terminate()
        self.close()

    def _fill_buffer(self, in_data, frame_count, time_info, status_flags):
        """Continuously collect data from the audio stream, into the buffer."""
        self._buff.put(in_data)
        return None, pyaudio.paContinue

    def close(self):
        """Signal the generator to terminate.

        Stops the audio stream and waits for the buffer to flush.
        """
        if not self.closed:
            self._audio_stream.stop_stream()
            self._audio_stream.close()
            self.closed = True
            self._buff.put(None)
            self._audio_interface.terminate()

    def generator(self):
        while not self.closed:
            # Use a blocking get() to ensure there's at least one chunk of
            # data, and stop iteration if the chunk is None, indicating the
            # end of the audio stream.
            chunk = self._buff.get()
            if chunk is None:
                return
            data = [chunk]

            # Now consume whatever other data's still buffered.
            while True:
                try:
                    chunk = self._buff.get(block=False)
                    if chunk is None:
                        return
                    data.append(chunk)
                except queue.Empty:
                    break

            data = b"".join(data)

            data_np = np.frombuffer(data, dtype=np.int16)
            data_np = data_np.astype(np.int32)
            data_diff = np.max(data_np) - np.min(data_np)

            data_busy = data_diff > self._stt.init_args.speech_threshold

            with self._stt.main_lock:
                state = self._stt.state
                state_time = self._stt.state_time

            now = time.time()

            next_state = state

            if state == 'READY' and (not data_busy):
                pass
            elif state == 'READY' and data_busy:
                next_state = 'PROCESS_EMPTY'
            elif state == 'PROCESS_EMPTY' and (not data_busy):
                if (now - state_time) > self._stt.init_args.speech_timeout:
                    next_state = 'READY'
            elif state == 'PROCESS_EMPTY' and data_busy:
                next_state = 'PROCESS_EMPTY!'
            elif state == 'PROCESS_BUSY':
                pass
            elif state == 'FINISHED' and (not data_busy):
                if (now - state_time) > self._stt.init_args.speech_timeout:
                    next_state = 'READY'
            elif state == 'FINISHED' and data_busy:
                next_state = 'PROCESS_EMPTY'

            if next_state != state:
                next_state = next_state.replace('!', '')
                with self._stt.main_lock:
                    self._stt.state = next_state
                    self._stt.state_time = now
            
            print(f'{state} > {next_state}')

            if next_state in ['PROCESS_EMPTY', 'PROCESS_BUSY','FINISHED']:
                d_list = []
                while self._ready_queue:
                    d_list.append(self._ready_queue.popleft())
                d_list.append(data)
                data = b"".join(d_list)
                yield data
            else:
                self._ready_queue.append(data)
                while len(self._ready_queue) > 5:
                    self._ready_queue.popleft()

            if next_state == 'READY' and (state != next_state):
                return

            # yield data

def wait_content(generator):
    n = next(generator)
    return g(n, generator)

def g(n, generator):
    yield n
    for i in generator:
        yield i
