import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView

app = QApplication(sys.argv)
view = QWebEngineView()
view.setHtml("<h1>Test</h1>")
view.show()
sys.exit(app.exec())