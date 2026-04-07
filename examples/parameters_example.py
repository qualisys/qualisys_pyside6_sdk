"""
Parameters example - Request and display QTM configuration
"""

import sys
import xml.etree.ElementTree as ET

from PySide6.QtCore import QCoreApplication

from qtm_rt_pyside6 import QTMConnection


class ParametersApp:
    def __init__(self):
        self.connection = QTMConnection()

        # Connect signals
        self.connection.connected.connect(self.on_connected)
        self.connection.disconnected.connect(self.on_disconnected)
        self.connection.error.connect(self.on_error)

        # Use onResponse helper for cleaner code
        self.connection.onResponse("qtmversion", self.on_version)
        self.connection.onResponse("getparameters", self.on_parameters)

    def start(self, host: str = "127.0.0.1"):
        print(f"Connecting to {host}...")
        self.connection.connectToHost(host)

    def on_connected(self):
        print("Connected!")
        print()
        # Request version first
        self.connection.getQtmVersion()

    def on_version(self, version: bytes):
        print(f"QTM Version: {version.decode()}")
        print()
        # Now request 3D, 6D, and skeleton parameters
        self.connection.getParameters(["3d", "6d", "skeleton"])

    def on_parameters(self, xml_str: str):
        print("Parameters received:")
        print("-" * 40)

        try:
            root = ET.fromstring(xml_str)

            # Parse 3D markers
            the_3d = root.find(".//The_3D")
            if the_3d is not None:
                print("3D Markers:")
                for label in the_3d.findall(".//Label"):
                    name = label.find("Name")
                    if name is not None:
                        print(f"  - {name.text}")

            # Parse 6DOF bodies
            the_6d = root.find(".//The_6D")
            if the_6d is not None:
                print("\n6DOF Bodies:")
                for body in the_6d.findall(".//Body"):
                    name = body.find("Name")
                    if name is not None:
                        print(f"  - {name.text}")
            the_skeleton = root.find(".//The_Skeleton")
            if the_skeleton is not None:
                print("\nSkeletons:")
                for skeleton in the_skeleton.findall(".//Skeleton"):
                    name = skeleton.find("Name")
                    if name is not None:
                        print(f"  - {name.text}")
        except ET.ParseError as e:
            print(f"XML parse error: {e}")

        print()
        self.connection.disconnect()

    def on_disconnected(self):
        print("Disconnected")
        QCoreApplication.quit()

    def on_error(self, error: str):
        print(f"Error: {error}")
        QCoreApplication.quit()


if __name__ == "__main__":
    app = QCoreApplication(sys.argv)

    params_app = ParametersApp()
    params_app.start()

    sys.exit(app.exec())
