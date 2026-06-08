import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


class ProcessSupervisor:
    IMPORTANT_LOG_MARKERS = (
        "address already in use",
        "error",
        "errno",
        "failed",
        "traceback",
        "valueerror",
    )

    def __init__(
        self,
        *,
        popen_factory=None,
        health_probe=None,
        sleeper=None,
    ):
        self.popen_factory = popen_factory or subprocess.Popen
        self.health_probe = health_probe or self._probe_url
        self.sleeper = sleeper or time.sleep
        self.process = None
        self.command = []
        self.output_path = ""
        self._output_file = None
        self.status = "stopped"
        self.error_message = ""

    def start(self, command, *, health_urls=None, timeout_seconds=30, env=None):
        if self.is_running():
            return True

        self.command = list(command)
        self.error_message = ""
        self.status = "starting"

        try:
            self._open_output_file()
            self.process = self.popen_factory(
                self.command,
                stdout=self._output_file,
                stderr=subprocess.STDOUT,
                **({"env": env} if env else {}),
            )
        except OSError as error:
            self._close_output_file()
            self.status = "error"
            self.error_message = str(error)
            return False

        if not health_urls:
            self.status = "ready"
            return True

        if self.wait_until_ready(health_urls, timeout_seconds=timeout_seconds):
            self.status = "ready"
            return True

        if not self.error_message:
            self.error_message = "Runtime process did not become ready before timeout."
        self.stop()
        self.status = "error"
        return False

    def stop(self, *, timeout_seconds=5):
        if not self.process:
            self._close_output_file()
            self.status = "stopped"
            return

        if self.is_running():
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=timeout_seconds)

        self.process = None
        self._close_output_file()
        self.status = "stopped"

    def is_running(self):
        return bool(self.process and self.process.poll() is None)

    def wait_until_ready(self, health_urls, *, timeout_seconds=30):
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if not self.is_running():
                self.error_message = self._build_exit_error_message()
                return False

            for url in health_urls:
                if self.health_probe(url):
                    return True

            self.sleeper(0.25)

        return False

    def _open_output_file(self):
        self._close_output_file()
        self._output_file = tempfile.NamedTemporaryFile(
            prefix="horizone-runtime-",
            suffix=".log",
            mode="w+b",
            delete=False,
        )
        self.output_path = self._output_file.name

    def _close_output_file(self):
        if self._output_file:
            self._output_file.close()
            self._output_file = None

    def _build_exit_error_message(self):
        output = self._read_output_tail()
        if output:
            return f"Runtime process exited before becoming ready. Last log lines: {output}"
        return "Runtime process exited before becoming ready."

    def _read_output_tail(self, *, max_bytes=4096):
        if not self.output_path:
            return ""

        try:
            with open(self.output_path, "rb") as output_file:
                output_file.seek(0, 2)
                size = output_file.tell()
                output_file.seek(max(0, size - max_bytes))
                data = output_file.read()
        except OSError:
            return ""

        output = data.decode("utf-8", errors="replace")
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        important_lines = [
            self._compact_log_line(line)
            for line in lines
            if self._is_important_log_line(line)
        ]
        if important_lines:
            return "\n".join(important_lines[-8:])

        return "\n".join(self._compact_log_line(line) for line in lines[-8:])

    def _is_important_log_line(self, line):
        lowered = line.lower()
        return any(marker in lowered for marker in self.IMPORTANT_LOG_MARKERS)

    def _compact_log_line(self, line, *, max_length=240):
        if len(line) <= max_length:
            return line
        return f"{line[:max_length - 3]}..."

    def _probe_url(self, url):
        try:
            with urlopen(url, timeout=1) as response:
                return 200 <= response.status < 500
        except (HTTPError, URLError, TimeoutError):
            return False
