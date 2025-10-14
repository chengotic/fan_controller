from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSlider
from PyQt6.QtCore import Qt
import sys

class Window(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fan Control GUI")

        self.label = QLabel("CPU target: 60°C")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(40, 100)
        self.slider.setValue(60)
        self.slider.valueChanged.connect(self.update_label)

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        self.setLayout(layout)

    def update_label(self, value):
        self.label.setText(f"CPU target: {value}°C")

app = QApplication(sys.argv)
win = Window()
win.show()
app.exec()
