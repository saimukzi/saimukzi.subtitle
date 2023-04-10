import copy
import hashlib
import json
import pyaudio

RATE = 16000
CHUNK = int(RATE / 10)  # 100ms

class AudioListener(object):

    def __init__(self, runtime):
        self.runtime = runtime
        self.init_args = runtime.init_args

        self._audio_interface = None
        self._audio_stream = None

    def start(self):
        print('Starting audio listener...')
        assert(self._audio_stream is None)
        assert(self._audio_interface is None)

        audio_input_device_list = get_audio_input_device_list()
        audio_input_device_list = filter(lambda info: info['hash']==self.runtime.audio_input_device_hash, audio_input_device_list)
        audio_input_device_list = list(audio_input_device_list)

        if len(audio_input_device_list) <= 0:
            print('No audio input device found')
            return False
        
        self._audio_interface = pyaudio.PyAudio()

        info = audio_input_device_list[0]
        print(info)

        self._audio_stream = self._audio_interface.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=RATE,
            input=True,
            input_device_index = info['index'],
            frames_per_buffer=CHUNK,
            stream_callback=self._stream_callback,
        )

        self.runtime.update_status('audio_input_device', info['name'])

        print('Audio listener started')

    def stop(self):
        print('Stopping audio listener...')
        if self._audio_stream is not None:
            self._audio_stream.stop_stream()
            self._audio_stream.close()
            self._audio_stream = None
            self._audio_interface.terminate()
            self._audio_interface = None
        if self.runtime.translation_agent is not None:
            self.runtime.translation_agent.on_audio_listener_stopped()
        print('Audio listener stopped')

    def _stream_callback(self, in_data, frame_count, time_info, status_flags):
        if self.runtime.running:
            if self.runtime.translation_agent is not None:
                self.runtime.translation_agent.on_audio_listener_data(in_data)
        return None, pyaudio.paContinue

def get_audio_input_device_list():
    audio_interface = pyaudio.PyAudio()
    ret = _get_audio_input_device_list(audio_interface)
    audio_interface.terminate()
    return ret

def _get_audio_input_device_list(audio_interface):
    device_list = []
    for i in range(audio_interface.get_device_count()):
        info = audio_interface.get_device_info_by_index(i)
        if info['maxInputChannels'] <= 0: continue
        try:
            if not audio_interface.is_format_supported(
                rate=RATE,
                input_device=info['index'],
                input_channels=1,
                input_format=pyaudio.paInt16,
            ):
                continue
        except:
            continue
        info0 = copy.deepcopy(info)
        del info0['index']
        info0_json = json.dumps(info0, sort_keys=True)
        info0_json_hash = hashlib.md5(info0_json.encode('utf-8')).hexdigest()
        info['hash'] = info0_json_hash
        device_list.append(info)
    return device_list
