import sys
import queue
import serial
import serial.tools.list_ports

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QDockWidget, QPlainTextEdit,
    QWidget, QDialog, QVBoxLayout, QLabel, QSlider,
    QPushButton, QFormLayout, QMessageBox, QComboBox
)
from PySide6.QtGui import QAction, QKeyEvent, QKeySequence
from PySide6.QtCore import Qt, QThread, Signal


class SliderDialog(QDialog):
    def __init__(self, title, minimum, maximum, value, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(320, 140)
        layout = QVBoxLayout(self)
        self.label = QLabel(f"{title}: {value}")
        layout.addWidget(self.label)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self.update_label)

    def update_label(self, value):
        self.label.setText(f"{self.windowTitle()}: {value}")

    def get_value(self):
        return self.slider.value()


class QKeySequenceHelper:
    @staticmethod
    def key_to_string(key):
        text = QKeySequence(key).toString(QKeySequence.NativeText)
        if text:
            return text

        special_keys = {
            Qt.Key_Up: "Up Arrow",
            Qt.Key_Down: "Down Arrow",
            Qt.Key_Left: "Left Arrow",
            Qt.Key_Right: "Right Arrow",
            Qt.Key_Shift: "Shift",
            Qt.Key_Control: "Ctrl",
            Qt.Key_Alt: "Alt",
            Qt.Key_Meta: "Meta",
            Qt.Key_Space: "Space",
            Qt.Key_Return: "Enter",
            Qt.Key_Enter: "Enter",
            Qt.Key_Escape: "Esc",
            Qt.Key_Tab: "Tab",
            Qt.Key_Backspace: "Backspace",
        }

        if key in special_keys:
            return special_keys[key]

        key_event = QKeyEvent(QKeyEvent.KeyPress, key, Qt.NoModifier)
        raw_text = key_event.text()
        if raw_text:
            return raw_text.upper()

        return "Unknown"


class KeyCaptureDialog(QDialog):
    def __init__(self, action_name, current_key_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Set Keybind - {action_name}")
        self.resize(320, 120)
        self.captured_key = None
        layout = QVBoxLayout(self)
        self.label = QLabel(f"Press a new key for {action_name}\nCurrent: {current_key_name}")
        layout.addWidget(self.label)

    def keyPressEvent(self, event: QKeyEvent):
        self.captured_key = event.key()
        self.accept()


class KeybindsDialog(QDialog):
    keybind_updated = Signal(str, int)

    def __init__(self, bindings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configure Keybinds")
        self.resize(420, 420)
        self.bindings = bindings
        self.value_labels = {}
        layout = QVBoxLayout(self)
        form = QFormLayout()

        for action_name, key_code in self.bindings.items():
            row_widget = QWidget()
            row_layout = QVBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            key_label = QLabel(QKeySequenceHelper.key_to_string(key_code))
            change_button = QPushButton(f"Change {action_name}")
            change_button.clicked.connect(
                lambda checked=False, action=action_name: self.change_keybind(action)
            )
            row_layout.addWidget(key_label)
            row_layout.addWidget(change_button)
            self.value_labels[action_name] = key_label
            form.addRow(action_name, row_widget)

        layout.addLayout(form)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)

    def change_keybind(self, action_name):
        current_key = self.bindings[action_name]
        current_key_name = QKeySequenceHelper.key_to_string(current_key)
        dialog = KeyCaptureDialog(action_name, current_key_name, self)
        if dialog.exec():
            new_key = dialog.captured_key
            if new_key is None:
                return
            for existing_action, existing_key in self.bindings.items():
                if existing_action != action_name and existing_key == new_key:
                    QMessageBox.warning(
                        self, "Duplicate Key",
                        f"'{QKeySequenceHelper.key_to_string(new_key)}' is already assigned to {existing_action}."
                    )
                    return
            self.bindings[action_name] = new_key
            self.value_labels[action_name].setText(QKeySequenceHelper.key_to_string(new_key))
            self.keybind_updated.emit(action_name, new_key)


class ComPortDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select COM Port")
        self.resize(360, 140)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select the COM port for your ESP32:"))

        self.combo = QComboBox()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.combo.addItem(f"{port.device} — {port.description}", port.device)

        if self.combo.count() == 0:
            self.combo.addItem("No COM ports found", None)

        layout.addWidget(self.combo)

        ok_btn = QPushButton("Connect")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(ok_btn)
        layout.addWidget(cancel_btn)

    def get_port(self):
        return self.combo.currentData()


class SerialWorker(QThread):
    line_received = Signal(str)
    error = Signal(str)
    connected = Signal(bool, str)

    def __init__(self, port: str, parent=None):
        super().__init__(parent)
        self.port = port
        self._running = True
        self._write_queue = queue.Queue()
        self.ser = None

    def stop(self):
        self._running = False

    def enqueue(self, cmd: str):
        self._write_queue.put(cmd)

    def run(self):
        try:
            self.ser = serial.Serial(self.port, baudrate=115200, timeout=0.1)
            self.connected.emit(True, f"Connected to {self.port} at 115200 baud.")
        except Exception as e:
            self.connected.emit(False, f"Failed to open {self.port}: {e}")
            return

        while self._running:
            try:
                while not self._write_queue.empty():
                    cmd = self._write_queue.get_nowait()
                    self.ser.write(cmd.encode("utf-8"))

                if self.ser.in_waiting:
                    line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                    if line:
                        self.line_received.emit(line)

            except Exception as e:
                self.error.emit(f"Serial error: {e}")
                break

            self.msleep(10)

        try:
            if self.ser and self.ser.is_open:
                self.ser.close()
        except Exception:
            pass


class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ENEL-300 Controller")
        self.resize(900, 600)

        self.steering_value = 50
        self.acceleration_value = 50
        self.gear_value = 3

        self.serial_worker = None

        self.active_inputs = set()
        self.headlights_on = False
        self.position_lock_on = False

        self.keybinds = {
            "UP":               Qt.Key_W,
            "LEFT":             Qt.Key_A,
            "BACK":             Qt.Key_S,
            "RIGHT":            Qt.Key_D,
            "SPEED UP":         Qt.Key_Up,
            "SPEED DOWN":       Qt.Key_Down,
            "POSITION LOCK":    Qt.Key_N,
            "DISTANCE SENSE":   Qt.Key_M,
            "HEADLIGHT TOGGLE": Qt.Key_L,
            "METAL DETECTED":   Qt.Key_P,
        }

        self.action_commands = {
            "UP":               "W",
            "LEFT":             "A",
            "BACK":             "S",
            "RIGHT":            "D",
            "SPEED UP":         "U",
            "SPEED DOWN":       "J",
            "POSITION LOCK":    "N",
            "DISTANCE SENSE":   "M",
            "HEADLIGHT TOGGLE": "L",
            "METAL DETECTED":   "P",
        }

        self.setup_central_area()
        self.setup_menu()
        self.setup_serial_monitor()

        self.setFocusPolicy(Qt.StrongFocus)
        self.central.setFocusPolicy(Qt.StrongFocus)
        self.central.setFocus()

        self.append_serial("Keyboard input ready.")
        self.append_serial("Pair ESP32 via Windows Bluetooth settings first, then use Connect Device.")
        self.print_current_keybinds()

    def setup_central_area(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)

    def setup_menu(self):
        menu_bar = self.menuBar()

        connect_menu = menu_bar.addMenu("Connect")
        self.connect_action = QAction("Connect Device", self)
        self.disconnect_action = QAction("Disconnect Device", self)
        connect_menu.addAction(self.connect_action)
        connect_menu.addAction(self.disconnect_action)

        view_menu = menu_bar.addMenu("View")
        self.serial_monitor_action = QAction("Open Serial Monitor", self)
        self.crash_reports_action = QAction("Crash Reports", self)
        self.telemetry_action = QAction("Telemetry", self)
        view_menu.addAction(self.serial_monitor_action)
        view_menu.addAction(self.crash_reports_action)
        view_menu.addAction(self.telemetry_action)

        config_menu = menu_bar.addMenu("Config")
        self.steering_sensitivity_action = QAction("Steering Sensitivity", self)
        self.acceleration_sensitivity_action = QAction("Acceleration Sensitivity", self)
        self.gear_action = QAction("Gear", self)
        self.keybinds_action = QAction("Keybinds", self)
        config_menu.addAction(self.steering_sensitivity_action)
        config_menu.addAction(self.acceleration_sensitivity_action)
        config_menu.addAction(self.gear_action)
        config_menu.addAction(self.keybinds_action)

        self.connect_action.triggered.connect(self.connect_device)
        self.disconnect_action.triggered.connect(self.disconnect_device)
        self.serial_monitor_action.triggered.connect(self.toggle_serial_monitor)
        self.crash_reports_action.triggered.connect(self.view_crash_reports)
        self.telemetry_action.triggered.connect(self.view_telemetry)
        self.steering_sensitivity_action.triggered.connect(self.open_steering_sensitivity)
        self.acceleration_sensitivity_action.triggered.connect(self.open_acceleration_sensitivity)
        self.gear_action.triggered.connect(self.open_gear_config)
        self.keybinds_action.triggered.connect(self.open_keybinds_config)

    def setup_serial_monitor(self):
        self.serial_dock = QDockWidget("Serial Monitor", self)
        self.serial_dock.setAllowedAreas(Qt.BottomDockWidgetArea)

        self.serial_output = QPlainTextEdit()
        self.serial_output.setReadOnly(True)
        self.serial_output.setPlaceholderText("Serial output will appear here...")
        self.serial_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #000000;
                color: #ffffff;
                border: 1px solid #333333;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12pt;
                selection-background-color: #444444;
            }
        """)

        self.serial_dock.setWidget(self.serial_output)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.serial_dock)
        self.serial_dock.hide()
        self.serial_dock.visibilityChanged.connect(self.update_serial_menu_text)

    def append_serial(self, text):
        self.serial_output.appendPlainText(text)

    def show_serial_monitor(self):
        self.serial_dock.show()
        self.serial_dock.raise_()
        self.resizeDocks([self.serial_dock], [int(self.height() * 0.4)], Qt.Vertical)

    def toggle_serial_monitor(self):
        if self.serial_dock.isVisible():
            self.serial_dock.hide()
        else:
            self.show_serial_monitor()
            self.append_serial("Serial monitor opened")

    def update_serial_menu_text(self, visible):
        if visible:
            self.serial_monitor_action.setText("Close Serial Monitor")
        else:
            self.serial_monitor_action.setText("Open Serial Monitor")

    def connect_device(self):
        self.show_serial_monitor()

        if self.serial_worker and self.serial_worker.isRunning():
            self.append_serial("Already connected.")
            return

        dialog = ComPortDialog(self)
        if dialog.exec() != QDialog.Accepted:
            self.append_serial("Connect cancelled.")
            return

        port = dialog.get_port()
        if not port:
            self.append_serial("No port selected.")
            return

        self.append_serial(f"Connecting to {port}...")
        self.serial_worker = SerialWorker(port)
        self.serial_worker.connected.connect(self.on_connected)
        self.serial_worker.line_received.connect(self.on_esp_message)
        self.serial_worker.error.connect(self.on_serial_error)
        self.serial_worker.start()
        self.setFocus()

    def on_connected(self, success: bool, message: str):
        self.append_serial(message)
        if not success:
            self.serial_worker = None

    def disconnect_device(self):
        self.show_serial_monitor()

        if self.serial_worker:
            self.serial_worker.stop()
            self.serial_worker.wait(3000)
            self.serial_worker = None
            self.append_serial("Disconnected.")
        else:
            self.append_serial("No active connection.")

        self.setFocus()

    def send_command(self, cmd: str):
        if self.serial_worker and self.serial_worker.isRunning():
            self.serial_worker.enqueue(cmd)
        else:
            self.append_serial("Not connected — command not sent.")

    def on_esp_message(self, line: str):
        self.append_serial(f"ESP32: {line}")

    def on_serial_error(self, msg: str):
        self.append_serial(msg)
        self.serial_worker = None

    def view_crash_reports(self):
        self.append_serial("Crash Reports clicked")

    def view_telemetry(self):
        self.append_serial("Telemetry clicked")

    def open_steering_sensitivity(self):
        dialog = SliderDialog("Steering Sensitivity", 0, 100, self.steering_value, self)
        dialog.exec()
        self.steering_value = dialog.get_value()
        self.append_serial(f"Steering Sensitivity set to {self.steering_value}")
        self.setFocus()

    def open_acceleration_sensitivity(self):
        dialog = SliderDialog("Acceleration Sensitivity", 0, 100, self.acceleration_value, self)
        dialog.exec()
        self.acceleration_value = dialog.get_value()
        self.append_serial(f"Acceleration Sensitivity set to {self.acceleration_value}")
        self.setFocus()

    def open_gear_config(self):
        dialog = SliderDialog("Gear", 1, 5, self.gear_value, self)
        dialog.exec()
        self.gear_value = dialog.get_value()
        self.append_serial(f"Gear set to {self.gear_value}")
        self.setFocus()

    def open_keybinds_config(self):
        dialog = KeybindsDialog(dict(self.keybinds), self)
        dialog.keybind_updated.connect(self.update_keybind)
        dialog.exec()
        self.setFocus()

    def update_keybind(self, action_name, key_code):
        self.keybinds[action_name] = key_code
        self.append_serial(
            f"Keybind updated: {action_name} -> {QKeySequenceHelper.key_to_string(key_code)}"
        )

    def print_current_keybinds(self):
        self.append_serial("Current keybinds:")
        for action_name, key_code in self.keybinds.items():
            self.append_serial(f"  {action_name} -> {QKeySequenceHelper.key_to_string(key_code)}")

    def get_action_for_key(self, key):
        for action_name, bound_key in self.keybinds.items():
            if bound_key == key:
                return action_name
        return None

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        action_name = self.get_action_for_key(key)

        if action_name is not None:
            self.show_serial_monitor()

            if action_name in ("HEADLIGHT TOGGLE", "POSITION LOCK", "DISTANCE SENSE"):
                if key not in self.active_inputs:
                    self.active_inputs.add(key)

                    if action_name == "HEADLIGHT TOGGLE":
                        self.headlights_on = not self.headlights_on
                        state = "ON" if self.headlights_on else "OFF"
                        self.append_serial(f"INPUT TOGGLED: HEADLIGHT TOGGLE -> HEADLIGHTS {state}")

                    elif action_name == "POSITION LOCK":
                        self.position_lock_on = not self.position_lock_on
                        state = "ON" if self.position_lock_on else "OFF"
                        self.append_serial(f"INPUT TOGGLED: POSITION LOCK -> POSITION LOCK {state}")

                    elif action_name == "DISTANCE SENSE":
                        self.append_serial("INPUT TOGGLED: DISTANCE SENSE")

                    cmd = self.action_commands.get(action_name)
                    if cmd:
                        self.send_command(cmd)

                event.accept()
                return

            if key not in self.active_inputs:
                self.active_inputs.add(key)
                self.append_serial(
                    f"INPUT PRESSED: {action_name} ({QKeySequenceHelper.key_to_string(key)})"
                )
                cmd = self.action_commands.get(action_name)
                if cmd:
                    self.send_command(cmd)

            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        key = event.key()
        action_name = self.get_action_for_key(key)

        if action_name is not None:
            if key in self.active_inputs:
                self.active_inputs.remove(key)

                if action_name in ("UP", "LEFT", "BACK", "RIGHT", "METAL DETECTED"):
                    self.show_serial_monitor()
                    self.append_serial(
                        f"INPUT RELEASED: {action_name} ({QKeySequenceHelper.key_to_string(key)})"
                    )
                    if action_name == "METAL DETECTED":
                        self.send_command("X")
                    else:
                        self.send_command("Q")

            event.accept()
            return

        super().keyReleaseEvent(event)

    def closeEvent(self, event):
        self.disconnect_device()
        event.accept()


app = QApplication(sys.argv)
window = MyWindow()
window.show()
app.exec()