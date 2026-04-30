from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except Exception as exc:
        print("PySide6 is required to run the desktop app.")
        print(str(exc))
        return 1

    from app_window import TakeoffMainWindow

    app = QApplication(sys.argv)
    window = TakeoffMainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
