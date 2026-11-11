"""Audio-session domain service. Owns every native Recorder call on ONE worker.

Bundled into the legacy single-file Pythonista release for compatibility.
No UI, AI, task database, or shortcuts dependency.
"""
import threading as _voice_threading
import os as _voice_os
import uuid as _voice_uuid

class _VoiceSession:
    def __init__(self, folder, stage, progress, on_text, on_error, on_done):
        self.folder = folder
        self.stage = stage
        self.progress = progress
        self.on_text = on_text
        self.on_error = on_error
        self.on_done = on_done
        self.stop_event = _voice_threading.Event()
        self.cancel_event = _voice_threading.Event()
        self._lock = _voice_threading.RLock()
        self._state = 'idle'
        self.thread = None

    def start(self):
        with self._lock:
            if self._state != 'idle':
                return False
            self._state = 'starting'
            self.thread = _voice_threading.Thread(target=self._run, daemon=True,
                                                   name='PYVA-AudioOwner')
            try:
                self.thread.start()
            except Exception:
                self._state = 'idle'
                raise
        return True

    def stop(self):
        with self._lock:
            if self._state not in ('starting', 'recording'):
                return False
            self._state = 'stopping'
            self.stop_event.set()
        return True

    def cancel(self):
        with self._lock:
            if self._state == 'idle':
                return False
            self._state = 'cancelling'
            self.cancel_event.set()
            self.stop_event.set()
        return True

    def _safe_progress(self, value):
        try:
            self.progress(value)
        except Exception:
            pass

    def _safe_stage(self, value):
        try:
            self.stage(value)
        except Exception:
            pass

    def _run(self):
        recorder = None
        path = None
        try:
            if self.cancel_event.is_set():
                return
            import sound
            _voice_os.makedirs(self.folder, exist_ok=True)
            path = _voice_os.path.join(self.folder,
                       'chat_voice_'+_voice_uuid.uuid4().hex[:12]+'.m4a')
            self._safe_stage('recorder_start')
            recorder = sound.Recorder(path)
            recorder.record()
            with self._lock:
                if self._state == 'starting':
                    self._state = 'recording'
            if not self.cancel_event.is_set():
                self._safe_stage('recording')
                self._safe_progress('recording')
            self.stop_event.wait()
            self._safe_stage('stop_enter')
            # Same thread creates, starts, stops and releases native recorder.
            closing = recorder
            recorder = None  # Never call stop twice if native stop raises.
            closing.stop()
            del closing
            self._safe_stage('audio_stopped')
            self._safe_progress('stopped')
            if self.cancel_event.wait(0.7):
                return
            if not path or not _voice_os.path.isfile(path) or _voice_os.path.getsize(path)<100:
                raise ValueError('empty_recording')
            self._safe_stage('recognizing')
            import speech
            languages = speech.get_recognition_languages()
            lang = next((v for v in languages
                         if v.lower().replace('_','-') in ('zh-cn','zh-hans-cn')), None)
            results = speech.recognize(path,lang) if lang else speech.recognize(path)
            if self.cancel_event.is_set():
                return
            phrase = str(results[0][0]).strip() if results and results[0] else ''
            if not phrase:
                raise ValueError('empty_transcript')
            self._safe_stage('recognized')
            self.on_text(phrase)
        except Exception as exc:
            if not self.cancel_event.is_set():
                try:
                    self.on_error(type(exc).__name__)
                except Exception:
                    pass
        finally:
            if recorder is not None:
                try:
                    recorder.stop()
                except Exception:
                    pass
                recorder = None
            if path:
                try:
                    _voice_os.remove(path)
                except OSError:
                    pass
            with self._lock:
                self._state = 'idle'
            self._safe_stage('idle')
            self._safe_progress('idle')
            try:
                self.on_done()
            except Exception:
                pass
