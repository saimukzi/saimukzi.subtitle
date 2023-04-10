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

        self._audio_interface = pyaudio.PyAudio()

        info = None
        for i in range(self._audio_interface.get_device_count()):
            info0 = self._audio_interface.get_device_info_by_index(i)
            if info0['maxInputChannels'] <= 0: continue
            if self.init_args.device not in info0['name']: continue
            try:
                if not self._audio_interface.is_format_supported(
                    rate=RATE,
                    input_device=info0['index'],
                    input_channels=1,
                    input_format=pyaudio.paInt16,
                ):
                    continue
            except:
                continue
            if info is not None:
                if info0['defaultLowInputLatency'] < info['defaultLowInputLatency']:
                    info = info0
            else:
                info = info0
        
        assert(info is not None)
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
