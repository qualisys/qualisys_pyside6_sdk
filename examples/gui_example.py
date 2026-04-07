"""
GUI Example - PySide6 application for streaming QTM data

Features:
- Discover QTM instances on network
- Connect/disconnect
- Stream 3D markers with live display
- Show frame rate and marker count
"""

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qtm_rt_pyside6 import QRTPacket, QTMConnection, QTMDiscovery


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QTM PySide6 SDK - GUI Example")
        self.setMinimumSize(800, 600)

        # QTM connection
        self.connection = QTMConnection(self)
        self.connection.connected.connect(self.on_connected)
        self.connection.disconnected.connect(self.on_disconnected)
        self.connection.error.connect(self.on_error)
        self.connection.packetReceived.connect(self.on_packet)

        # Discovery
        self.discovery = QTMDiscovery(self, timeout_ms=2000)
        self.discovery.discovered.connect(self.on_discovered)
        self.discovery.finished.connect(self.on_discovery_finished)

        # Frame rate calculation
        self.frame_count = 0
        self.fps_timer = QTimer(self)
        self.fps_timer.timeout.connect(self.update_fps)
        self.fps_timer.setInterval(1000)

        self.setup_ui()

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Connection group
        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout(conn_group)

        self.host_combo = QComboBox()
        self.host_combo.setEditable(True)
        self.host_combo.setMinimumWidth(200)
        self.host_combo.addItem("127.0.0.1")
        conn_layout.addWidget(QLabel("Host:"))
        conn_layout.addWidget(self.host_combo)

        conn_layout.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22223)
        conn_layout.addWidget(self.port_spin)

        self.discover_btn = QPushButton("Discover")
        self.discover_btn.clicked.connect(self.discover)
        conn_layout.addWidget(self.discover_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)

        conn_layout.addStretch()
        layout.addWidget(conn_group)

        # Streaming group
        stream_group = QGroupBox("Streaming")
        stream_layout = QHBoxLayout(stream_group)

        self.stream_btn = QPushButton("Start Stream")
        self.stream_btn.clicked.connect(self.toggle_stream)
        self.stream_btn.setEnabled(False)
        stream_layout.addWidget(self.stream_btn)

        stream_layout.addWidget(QLabel("Component:"))
        self.component_combo = QComboBox()
        self.component_combo.addItems(["3d", "6d", "6deuler", "analog", "force"])
        stream_layout.addWidget(self.component_combo)

        self.fps_label = QLabel("FPS: --")
        self.fps_label.setMinimumWidth(80)
        stream_layout.addWidget(self.fps_label)

        self.frame_label = QLabel("Frame: --")
        self.frame_label.setMinimumWidth(120)
        stream_layout.addWidget(self.frame_label)

        self.marker_count_label = QLabel("Markers: --")
        stream_layout.addWidget(self.marker_count_label)

        stream_layout.addStretch()
        layout.addWidget(stream_group)

        # Data table
        data_group = QGroupBox("Data")
        data_layout = QVBoxLayout(data_group)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Index", "X", "Y", "Z"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)
        data_layout.addWidget(self.table)

        layout.addWidget(data_group, stretch=1)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # State
        self._streaming = False

    def discover(self):
        """Start QTM discovery"""
        self.discover_btn.setEnabled(False)
        self.discover_btn.setText("Searching...")
        self.status_bar.showMessage("Discovering QTM instances...")
        self.discovery.start()

    def on_discovered(self, response):
        """Handle discovered QTM instance"""
        # Add to combo if not already present
        host = response.host
        for i in range(self.host_combo.count()):
            if self.host_combo.itemText(i) == host:
                return

        self.host_combo.addItem(host)
        self.status_bar.showMessage(f"Found: {response.info} at {host}:{response.port}")

    def on_discovery_finished(self):
        """Handle discovery completion"""
        self.discover_btn.setEnabled(True)
        self.discover_btn.setText("Discover")

    def toggle_connection(self):
        """Connect or disconnect from QTM"""
        if self.connection.isConnected():
            if self._streaming:
                self.toggle_stream()
            self.connection.disconnect()
        else:
            host = self.host_combo.currentText()
            port = self.port_spin.value()
            self.status_bar.showMessage(f"Connecting to {host}:{port}...")
            self.connect_btn.setEnabled(False)
            self.connection.connectToHost(host, port)

    def on_connected(self):
        """Handle successful connection"""
        self.connect_btn.setText("Disconnect")
        self.connect_btn.setEnabled(True)
        self.stream_btn.setEnabled(True)
        self.status_bar.showMessage("Connected")

    def on_disconnected(self):
        """Handle disconnection"""
        self.connect_btn.setText("Connect")
        self.connect_btn.setEnabled(True)
        self.stream_btn.setEnabled(False)
        self.stream_btn.setText("Start Stream")
        self._streaming = False
        self.fps_timer.stop()
        self.fps_label.setText("FPS: --")
        self.frame_label.setText("Frame: --")
        self.marker_count_label.setText("Markers: --")
        self.status_bar.showMessage("Disconnected")

    def on_error(self, error: str):
        """Handle connection error"""
        self.status_bar.showMessage(f"Error: {error}")
        self.connect_btn.setEnabled(True)

    def toggle_stream(self):
        """Start or stop streaming"""
        if self._streaming:
            self.connection.streamFramesStop()
            self.stream_btn.setText("Start Stream")
            self._streaming = False
            self.fps_timer.stop()
            self.fps_label.setText("FPS: --")
            self.status_bar.showMessage("Streaming stopped")
        else:
            component = self.component_combo.currentText()
            self.connection.streamFrames([component])
            self.stream_btn.setText("Stop Stream")
            self._streaming = True
            self.frame_count = 0
            self.fps_timer.start()
            self.status_bar.showMessage(f"Streaming {component}...")

    def on_packet(self, packet: QRTPacket):
        """Handle incoming data packet"""
        self.frame_count += 1
        self.frame_label.setText(f"Frame: {packet.framenumber}")

        component = self.component_combo.currentText()

        if component == "3d":
            self.display_3d_markers(packet)
        elif component in ("6d", "6deuler"):
            self.display_6d_bodies(packet, component)

    def display_3d_markers(self, packet: QRTPacket):
        """Display 3D marker data in table"""
        result = packet.get_3d_markers()
        if result is None:
            return

        header, markers = result
        self.marker_count_label.setText(f"Markers: {header.marker_count}")

        # Limit display to 50 markers for performance
        display_count = min(len(markers), 50)

        self.table.setRowCount(display_count)
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Index", "X", "Y", "Z"])

        for i, marker in enumerate(markers[:display_count]):
            self.table.setItem(i, 0, QTableWidgetItem(str(i)))
            self.table.setItem(i, 1, QTableWidgetItem(f"{marker.x:.1f}"))
            self.table.setItem(i, 2, QTableWidgetItem(f"{marker.y:.1f}"))
            self.table.setItem(i, 3, QTableWidgetItem(f"{marker.z:.1f}"))

    def display_6d_bodies(self, packet: QRTPacket, component: str):
        """Display 6DOF body data in table"""
        if component == "6deuler":
            result = packet.get_6d_euler()
        else:
            result = packet.get_6d()

        if result is None:
            return

        header, bodies = result
        self.marker_count_label.setText(f"Bodies: {header.body_count}")

        self.table.setRowCount(len(bodies))

        if component == "6deuler":
            self.table.setColumnCount(7)
            self.table.setHorizontalHeaderLabels(["Index", "X", "Y", "Z", "Roll", "Pitch", "Yaw"])

            for i, (pos, euler) in enumerate(bodies):
                self.table.setItem(i, 0, QTableWidgetItem(str(i)))
                self.table.setItem(i, 1, QTableWidgetItem(f"{pos.x:.1f}"))
                self.table.setItem(i, 2, QTableWidgetItem(f"{pos.y:.1f}"))
                self.table.setItem(i, 3, QTableWidgetItem(f"{pos.z:.1f}"))
                self.table.setItem(i, 4, QTableWidgetItem(f"{euler.a1:.1f}"))
                self.table.setItem(i, 5, QTableWidgetItem(f"{euler.a2:.1f}"))
                self.table.setItem(i, 6, QTableWidgetItem(f"{euler.a3:.1f}"))
        else:
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["Index", "X", "Y", "Z"])

            for i, (pos, _rotation) in enumerate(bodies):
                self.table.setItem(i, 0, QTableWidgetItem(str(i)))
                self.table.setItem(i, 1, QTableWidgetItem(f"{pos.x:.1f}"))
                self.table.setItem(i, 2, QTableWidgetItem(f"{pos.y:.1f}"))
                self.table.setItem(i, 3, QTableWidgetItem(f"{pos.z:.1f}"))

    def update_fps(self):
        """Update FPS display"""
        self.fps_label.setText(f"FPS: {self.frame_count}")
        self.frame_count = 0

    def closeEvent(self, event):
        """Clean up on close"""
        if self._streaming:
            self.connection.streamFramesStop()
        if self.connection.isConnected():
            self.connection.disconnect()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
