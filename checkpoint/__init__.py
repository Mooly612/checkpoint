"""Checkpoint: undo for your map styling. Core imports remain QGIS-free."""


def classFactory(iface):
    """QGIS plugin entry point, imported only when the plugin is enabled."""
    from .plugin import CheckpointPlugin
    return CheckpointPlugin(iface)
