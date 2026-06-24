# transcriber.py
import os
import time
import subprocess
import tempfile
import requests
from pathlib import Path


class AudioSplitter:
    """فایل صوتی را به تکه‌های کوچکتر تقسیم می‌کند."""

    def __init__(self, chunk_minutes: int = 5):
        self._chunk_sec = chunk_minutes * 60

    def get_duration(self, file_path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())

    def needs_split(self, file_path: str) -> bool:
        """چک می‌کند که آیا فایل نیاز به تقسیم دارد."""
        try:
            duration = self.get_duration(file_path)
            return duration > self._chunk_sec
        except Exception:
            return False

    def split(self, file_path: str) -> list[str]:
        """فایل را به چانک تقسیم می‌کند و مسیر چانک‌ها را برمی‌گرداند."""
        duration = self.get_duration(file_path)
        tmp_dir  = tempfile.mkdtemp()
        chunks   = []
        start    = 0

        while start < duration:
            out = os.path.join(tmp_dir, f"chunk_{int(start):06d}.mp3")
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(start),
                    "-i", file_path,
                    "-t", str(self._chunk_sec),
                    "-acodec", "libmp3lame",
                    "-ar", "16000",
                    "-ac", "1",
                    "-q:a", "4",
                    out,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            chunks.append(out)
            start += self._chunk_sec

        return chunks


class TranscriptionClient:
    """یک فایل صوتی را به متن تبدیل می‌کند."""

    def __init__(self, api_key: str, url: str, model: str,
                 max_retries: int = 4, language: str = "fa"):
        self._headers     = {"Authorization": f"Bearer {api_key}"}
        self._url         = url
        self._model       = model
        self._max_retries = max_retries
        self._language    = language

    def transcribe(self, file_path: str) -> str:
        last_err = None

        for attempt in range(1, self._max_retries + 1):
            try:
                with open(file_path, "rb") as f:
                    resp = requests.post(
                        self._url,
                        headers=self._headers,
                        files={"file": ("audio.mp3", f, "audio/mpeg")},
                        data={
                            "model":           self._model,
                            "language":        self._language,
                            "response_format": "text",
                            "temperature":     "0",
                        },
                        timeout=120,
                    )

                if resp.status_code == 200:
                    return resp.text.strip()

                if resp.status_code in (429, 500, 502, 503, 504):
                    wait = 2 ** attempt
                    time.sleep(wait)
                    last_err = f"HTTP {resp.status_code}"
                    continue

                raise RuntimeError(
                    f"HTTP {resp.status_code}: {resp.text[:200]}"
                )

            except requests.exceptions.Timeout:
                time.sleep(2 ** attempt)
                last_err = "Timeout"

            except requests.exceptions.ConnectionError:
                time.sleep(2 ** attempt)
                last_err = "ConnectionError"

        raise RuntimeError(
            f"بعد از {self._max_retries} تلاش: {last_err}"
        )


class SmartTranscriber:
    """
    اگر فایل کوتاه است → مستقیم می‌فرستد.
    اگر فایل بلند است و ffmpeg دارد → تقسیم می‌کند.
    """

    def __init__(self, api_key: str, url: str, model: str,
                 chunk_minutes: int = 5, delay: int = 3,
                 max_retries: int = 4, language: str = "fa",
                 progress_callback=None):

        self._client   = TranscriptionClient(
            api_key, url, model, max_retries, language
        )
        self._splitter = AudioSplitter(chunk_minutes)
        self._delay    = delay
        self._callback = progress_callback  # تابعی که پیشرفت را گزارش می‌دهد

    def _has_ffmpeg(self) -> bool:
        import shutil
        return shutil.which("ffmpeg") is not None

    def transcribe(self, file_path: str) -> str:
        """
        فایل صوتی را دریافت و متن آن را برمی‌گرداند.
        progress_callback(current, total, message) صدا زده می‌شود.
        """
        if self._callback:
            self._callback(0, 1, "در حال بررسی فایل...")

        # بررسی نیاز به split
        if self._has_ffmpeg() and self._splitter.needs_split(file_path):
            return self._transcribe_chunked(file_path)
        else:
            if self._callback:
                self._callback(0, 1, "در حال ارسال به API...")
            result = self._client.transcribe(file_path)
            if self._callback:
                self._callback(1, 1, "تمام شد ✅")
            return result

    def _transcribe_chunked(self, file_path: str) -> str:
        if self._callback:
            self._callback(0, 1, "در حال تقسیم فایل...")

        chunks = self._splitter.split(file_path)
        total  = len(chunks)
        results = []

        for i, chunk_path in enumerate(chunks):
            if self._callback:
                self._callback(
                    i, total,
                    f"بخش {i+1} از {total} در حال پردازش..."
                )
            try:
                text = self._client.transcribe(chunk_path)
                results.append(text)
                if i < total - 1:
                    time.sleep(self._delay)
            except Exception as e:
                results.append(f"[⚠️ بخش {i+1} ناموفق: {e}]")
            finally:
                if os.path.exists(chunk_path):
                    os.unlink(chunk_path)

        if self._callback:
            self._callback(total, total, "تمام شد ✅")

        return "\n\n".join(results)