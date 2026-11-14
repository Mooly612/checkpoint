"""Translation boundary shared by Qt UI and pure-Python descriptions.

English is the only shipped language. No unverified language support is claimed.
"""
try:
    from qgis.PyQt.QtCore import QCoreApplication
except ImportError:
    QCoreApplication = None


def tr(message):
    return QCoreApplication.translate('Checkpoint', message) if QCoreApplication else message
