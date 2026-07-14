import sys
from PyQt6.QtWidgets import QMainWindow, QApplication, QFileDialog
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtGui import QTextCursor
from PyQt6.uic import loadUi
from omegaconf import OmegaConf
from time import sleep
from process_one_tile import ICP_process


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
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.fn(*self.args, **self.kwargs)


# --------------------------------
# Main UI
# --------------------------------
class mainUI(QMainWindow):
    def __init__(self):
        super(mainUI, self).__init__()
        loadUi("src/gui.ui", self)

        # Browse buttons
        self.btn_epoch1.clicked.connect(lambda: self._browse(self.le_epoch1))
        self.btn_epoch2.clicked.connect(lambda: self._browse(self.le_epoch2))

        # Start button
        self.pushButton.clicked.connect(self.run_algorithm)

        # Redirect stdout to log box
        self.stream = Stream()
        self.stream.text_written.connect(self._write_log)
        sys.stdout = self.stream
        sys.stderr = self.stream

    def _write_log(self, text):
        self.log_box.moveCursor(QTextCursor.MoveOperation.End)
        self.log_box.insertPlainText(text)
        self.log_box.moveCursor(QTextCursor.MoveOperation.End)

    def _browse(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select file", "",
            "Point Clouds (*.las *.laz *.pcd *.ply);;All files (*)"
        )
        if path:
            line_edit.setText(path)

    def run_algorithm(self):
        src_pc1 = self.le_epoch1.text()
        src_pc2 = self.le_epoch2.text()

        conf = OmegaConf.load("./config/one_tile.yaml")
        OmegaConf.update(conf, 'data.src_pc1', src_pc1)
        OmegaConf.update(conf, 'data.src_pc2', src_pc2)

        self.pushButton.setEnabled(False)
        # self.worker = WorkerThread(test)
        self.worker = WorkerThread(ICP_process, conf, conf.args.verbose)
        self.worker.finished.connect(lambda: self.pushButton.setEnabled(True))
        self.worker.start()

    def closeEvent(self, event):
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        super().closeEvent(event)


def test():
    for i in range(10):
        print(i)
        sleep(0.2)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    ui = mainUI()
    ui.show()
    app.exec()