"""Run the virtual meter:  python -m idm207meter [--replay capture.log]"""
import argparse
import sys

from PyQt6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main():
    ap = argparse.ArgumentParser(description="IDM207 virtual meter and datalogger")
    ap.add_argument("--replay", metavar="LOG", help="start replaying a capture log instead of a serial port")
    a, qt_args = ap.parse_known_args()
    app = QApplication([sys.argv[0]] + qt_args)
    w = MainWindow(replay_path=a.replay)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
