import os
import numpy as np
import pickle
import traceback
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer
from tkinter import messagebox
from ast import literal_eval
from pathvalidate import sanitize_filepath
from postprocessing import postprocessing
from src.postprocessing_utils import remove_A0

    
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


def browse(self, line_edit=None, file_types="Point Clouds (*.las *.laz *.pcd *.ply)"):
    src_of_search = os.path.dirname(line_edit.text()) if is_a_path(line_edit.text()) else ''
    path, _ = QFileDialog.getOpenFileName(
        self, "Select file", src_of_search,
        filter=f"{file_types};;All files (*)"
    )
    if path:
        if hasattr(line_edit, 'setText'):
            line_edit.setText(path)
        else:
            return path


def browse_folder(self, line_edit):
    src_of_search = os.path.dirname(line_edit.text()) if is_a_path(line_edit.text()) else ''
    path = QFileDialog.getExistingDirectory(
        self, "Select folder", src_of_search
    )
    if path:
        if hasattr(line_edit, 'setText'):
            line_edit.setText(path)
        else:
            return path


def test_value(self, test_res, object, scrollArea=None) -> bool:
    if test_res:
        return True
    else:
        self.blink_timer = Blinker(object, color_on="red", interval_ms=300, duration_ms=3000)
        self.blink_timer.start()
        if scrollArea != None:
            scrollArea.ensureWidgetVisible(object, xMargin=10, yMargin=10)

        return False


def run_postprocessing(conf):
    if conf.postprocessing.src_transforms == 'default':
        if conf.data.src_res == 'default':
            conf.data.src_res = os.path.join(os.path.dirname(conf.data.src_pc1), 'results')
        src_transforms = os.path.join(conf.data.src_res, f'{conf.data.res_prefix}_quadtree_transforms.pickle')
    else:
        src_transforms = conf.postprocessing.src_transforms

    # prepare paths
    src_out_gpkg = os.path.join(os.path.dirname(src_transforms), 'points_translate.gpkg')
    src_offset = os.path.join(os.path.dirname(src_transforms), 'offset.txt')

    with open(src_transforms, 'rb') as f:
        root = pickle.load(f)
    offset = np.loadtxt(src_offset, delimiter=',')

    # Postprocess with A0
    if conf.postprocessing.to_keep.initial_alignment in ['with', 'both']:
        print("Postprocessing with initial alignment (w_A0)")
        postprocessing(
            root=root, 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            to_keep=conf.postprocessing.to_keep,
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
            suffix='w_A0', 
            verbose=conf.postprocessing.verbose,
            )

    # Postprocess without A0:
    if conf.postprocessing.to_keep.initial_alignment in ['without', 'both']:
        print("\nPostprocessing without initial alignment (wo_A0)")
        A0_inv = np.linalg.inv(root.global_transform)
        remove_A0(root, A0_inv)
        postprocessing(
            root=root, 
            src_out_gpkg=src_out_gpkg, 
            offset=offset, 
            to_keep=conf.postprocessing.to_keep,
            absurd_dist_local=conf.postprocessing.absurd_dist_local,
            absurd_dist_global=conf.postprocessing.absurd_dist_global, 
            suffix='wo_A0', 
            verbose=conf.postprocessing.verbose,
            )
     
    
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
