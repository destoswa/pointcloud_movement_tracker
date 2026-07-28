import sys
import os
import traceback
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog, QLabel, QLineEdit, QTextEdit, QPlainTextEdit
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QTextCursor
from PyQt6.uic import loadUi
from omegaconf import OmegaConf
from tkinter import messagebox
from ast import literal_eval
import traceback as tb
from pathvalidate import sanitize_filepath


# --------------------------------
# Utils
# --------------------------------
def will_it_float(element: any) -> bool:
    #If you expect None to be passed:
    if element is None: 
        return False
    try:
        float(element)
        return True
    except ValueError:
        return False


def is_string_list(text: str) -> bool:
    try:
        result = literal_eval(text)
        return isinstance(result, list)
    except (ValueError, SyntaxError):
        return False


def is_a_path(filePath: str) -> bool:
    if os.path.exists(filePath):
        return True
    if filePath == sanitize_filepath(filePath):
        return True
    return False


def test_value(self, test_res, object, scrollArea=None) -> bool:
    if test_res:
        return True
    else:
        self.blink_timer = Blinker(object, color_on="red", interval_ms=300, duration_ms=3000)
        self.blink_timer.start()
        if scrollArea != None:
            scrollArea.ensureWidgetVisible(object, xMargin=10, yMargin=10)

        return False

    
# --------------------------------
# Stream redirector
# --------------------------------
class Stream(QObject):
    text_written = pyqtSignal(str)

    def write(self, text):
        self.text_written.emit(str(text))

    def flush(self):
        pass

    def isatty(self):
        return False  # needed for tqdm to not try terminal-specific behavior


# --------------------------------
# Worker thread
# --------------------------------
class WorkerThread(QThread):
    error_occurred = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.fn(*self.args, **self.kwargs)
        except Exception:
            tb = traceback.format_exc()
            self.error_occurred.emit(tb)


# --------------------------------
# Blinker
# --------------------------------
class Blinker(QObject):
    def __init__(self, widget, color_on="red", color_off="", 
                 interval_ms=300, duration_ms=3000, parent=None):
        super().__init__(parent)
        self.widget = widget
        self.color_on = color_on
        self.color_off = color_off
        self.state = False

        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self._toggle)
        self.blink_timer.setInterval(interval_ms)

        self.stop_timer = QTimer(self)
        self.stop_timer.setSingleShot(True)
        self.stop_timer.timeout.connect(self.stop)
        self.stop_timer.setInterval(duration_ms)

    def _toggle(self):
        self.state = not self.state
        self._apply_style()

    def _apply_style(self):
        style = f"border: 2px solid {self.color_on};" if self.state else self.color_off
        self.widget.setStyleSheet(style)

    def start(self):
        self.state = False
        self.blink_timer.start()
        self.stop_timer.start()

    def stop(self):
        self.blink_timer.stop()
        self.state = False
        self._apply_style()  # ensure it ends in the "off" state


def notimplementedyet():
    messagebox.showwarning("Warning", "Not implemented yet!") 
