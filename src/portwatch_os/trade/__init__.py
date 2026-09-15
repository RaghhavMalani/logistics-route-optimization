"""Trade: structural exposure of Indian cargo classes to what the world is doing.

No tonnage, no trade value, no estimate. See :mod:`.exposure`.
"""

from src.portwatch_os.trade.catalogue import CLASSES, LABELS, PortClass, classes_for, port_classes
from src.portwatch_os.trade.exposure import DISCLAIMER, EXPOSURE_KIND, chains_for, structural_exposure

__all__ = ["CLASSES", "DISCLAIMER", "EXPOSURE_KIND", "LABELS", "PortClass", "chains_for", "classes_for", "port_classes", "structural_exposure"]
