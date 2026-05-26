import platform
import shutil
import subprocess
from pathlib import Path


class NativeDialogError(Exception):
    pass


class NativeDialogUnavailableError(NativeDialogError):
    pass


class NativeDirectoryPickerService:
    def select_directory(self, initial_path=None, title=None):
        dialog_title = (title or "Choose workspace folder").strip()
        default_path = self._normalize_initial_path(initial_path)
        selected_path = self._open_directory_picker(dialog_title, default_path)

        if not selected_path:
            return None

        root_path = Path(selected_path).expanduser().resolve()
        if not root_path.exists() or not root_path.is_dir():
            raise NativeDialogError("The selected path is not a directory.")

        return {
            "root_path": str(root_path),
            "display_name": root_path.name or str(root_path),
        }

    def _open_directory_picker(self, title, initial_path):
        system = platform.system()
        if system == "Darwin":
            return self._open_macos_picker(title, initial_path)
        if system == "Windows":
            return self._open_windows_picker(title, initial_path)
        return self._open_linux_picker(title, initial_path)

    def _open_macos_picker(self, title, initial_path):
        osascript = shutil.which("osascript")
        if not osascript:
            return self._open_tkinter_picker(title, initial_path)

        title_literal = self._applescript_string(title)
        if initial_path:
            path_literal = self._applescript_string(str(initial_path))
            script = (
                f"set defaultFolder to POSIX file {path_literal}\n"
                f"POSIX path of (choose folder with prompt {title_literal} default location defaultFolder)"
            )
        else:
            script = f"POSIX path of (choose folder with prompt {title_literal})"

        result = subprocess.run(
            [osascript, "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        if "cancel" in result.stderr.lower():
            return None
        raise NativeDialogUnavailableError(
            result.stderr.strip() or "Could not open the directory picker."
        )

    def _open_windows_picker(self, title, initial_path):
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not powershell:
            return self._open_tkinter_picker(title, initial_path)

        script = """
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = $args[0]
$dialog.ShowNewFolderButton = $false
if ($args[1]) { $dialog.SelectedPath = $args[1] }
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Output $dialog.SelectedPath
}
""".strip()
        result = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
                title,
                str(initial_path or ""),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip() or None
        raise NativeDialogUnavailableError(
            result.stderr.strip() or "Could not open the directory picker."
        )

    def _open_linux_picker(self, title, initial_path):
        zenity = shutil.which("zenity")
        if zenity:
            command = [zenity, "--file-selection", "--directory", "--title", title]
            if initial_path:
                command.extend(["--filename", f"{initial_path}/"])
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip() or None
            if result.returncode == 1:
                return None
            raise NativeDialogUnavailableError(
                result.stderr.strip() or "Could not open the directory picker."
            )

        kdialog = shutil.which("kdialog")
        if kdialog:
            command = [kdialog, "--getexistingdirectory", str(initial_path or ""), "--title", title]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                return result.stdout.strip() or None
            if result.returncode == 1:
                return None
            raise NativeDialogUnavailableError(
                result.stderr.strip() or "Could not open the directory picker."
            )

        return self._open_tkinter_picker(title, initial_path)

    def _open_tkinter_picker(self, title, initial_path):
        try:
            import tkinter as tk
            from tkinter import filedialog
        except ImportError as error:
            raise NativeDialogUnavailableError(
                "Native directory picker support is not available on this system."
            ) from error

        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            selected_path = filedialog.askdirectory(
                title=title,
                initialdir=str(initial_path) if initial_path else None,
                mustexist=True,
            )
        except Exception as error:
            raise NativeDialogUnavailableError(
                "Could not open the native directory picker."
            ) from error
        finally:
            if "root" in locals():
                root.destroy()

        return selected_path or None

    def _normalize_initial_path(self, initial_path):
        if not initial_path:
            return None

        path = Path(str(initial_path)).expanduser()
        if path.exists() and path.is_dir():
            return path.resolve()
        return None

    def _applescript_string(self, value):
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
