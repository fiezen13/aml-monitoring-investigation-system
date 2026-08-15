"""MEGA-PNA edge classifier for the FIN-07 academic benchmark path.

The implementation follows Bilgi et al. (arXiv:2412.00241) and is limited to
the AML edge-classification setup used by FIN-07.  Production preprocessing is
intentionally kept outside this package.
"""

from .config import MegaPnaConfig
from .model import MegaPna

__all__ = ["MegaPna", "MegaPnaConfig"]
