import sys
# from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView


class MainWindow(QMainWindow):
    def __init__(self, port: int = 8000):
        super().__init__()
        self.setWindowTitle("Vue + PySide6 Frameless App")
        self.setGeometry(100, 100, 1200, 800)  # 視窗大小
        
        # 設定視窗為 frameless（無邊框）
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowSystemMenuHint)

        # 創建 QWebEngineView
        self.browser = QWebEngineView(self)
        self.browser.setUrl(QUrl(f"http://localhost:{port}/gui/"))
        self.browser.setGeometry(0, 0, 1200, 800)

        # 創建一個透明的 QWidget 只覆蓋視窗邊框
        self.transparent_widget = QWidget(self)
        self.transparent_widget.setGeometry(0, 0, 1200, 30)  # 只覆蓋視窗的頂部邊框
        # self.transparent_widget.setAttribute(Qt.WA_TransparentForMouseEvents)  # 不阻止鼠標事件

        # 設定為中心視窗
        self.setCentralWidget(self.browser)

        # 初始化拖動起始位置
        self._drag_position = None

    # 拖動事件：按下左鍵時記錄當前鼠標位置
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint()

    # 拖動事件：當鼠標移動時移動視窗
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_position:
            delta = event.globalPosition().toPoint() - self._drag_position
            self.move(self.pos() + delta)
            self._drag_position = event.globalPosition().toPoint()

    # 增加鼠標鬆開事件處理
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_position = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())