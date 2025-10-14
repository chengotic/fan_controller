from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QSlider, QGridLayout
from PyQt6.QtCore import Qt
import sys

class FanControlUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Fan Curve Config")

        layout = QGridLayout()
        self.setLayout(layout)

        def add_row(row, name):
            label_min = QLabel(f"{name} Min: 60°C")
            slider_min = QSlider(Qt.Orientation.Horizontal)
            slider_min.setRange(20, 100)
            slider_min.setValue(60)

            label_max = QLabel(f"{name} Max: 80°C")
            slider_max = QSlider(Qt.Orientation.Horizontal)
            slider_max.setRange(20, 100)
            slider_max.setValue(80)

            slider_min.valueChanged.connect(lambda v: label_min.setText(f"{name} Min: {v}°C"))
            slider_max.valueChanged.connect(lambda v: label_max.setText(f"{name} Max: {v}°C"))

            layout.addWidget(QLabel(name), row, 0)
            layout.addWidget(label_min, row, 1)
            layout.addWidget(slider_min, row, 2)
            layout.addWidget(label_max, row, 3)
            layout.addWidget(slider_max, row, 4)

            return slider_min, slider_max

        self.cpu_min, self.cpu_max = add_row(0, "CPU")
        self.gpu_min, self.gpu_max = add_row(1, "GPU")

app = QApplication(sys.argv)
win = FanControlUI()
win.show()
app.exec()
