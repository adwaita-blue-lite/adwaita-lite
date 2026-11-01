from gettext import gettext as _

from .about import AboutPage
from .accessibility import AccessibilityPage
from .appearance import AppearancePage
from .bluetooth import BluetoothPage
from .datetime import DateTimePage
from .default_apps import DefaultAppsPage
from .display import DisplayPage
from .keyboard import KeyboardPage
from .language import LanguagePage
from .mouse_touchpad import MouseTouchpadPage
from .network import NetworkPage
from .panel import PanelPage
from .power_lock import PowerLockPage
from .sound import SoundPage
from .users import UsersPage


def N_(s):
    """Mark for extraction without translating now."""
    return s


ALL_PAGES = [
    ("display-brightness-symbolic", N_("Appearance"), AppearancePage),
    ("video-display-symbolic", N_("Display"), DisplayPage),
    ("network-wireless-symbolic", N_("Network"), NetworkPage),
    ("bluetooth-symbolic", N_("Bluetooth"), BluetoothPage),
    ("view-app-grid-symbolic", N_("Panel"), PanelPage),
    ("input-mouse-symbolic", N_("Mouse & Touchpad"), MouseTouchpadPage),
    ("input-keyboard-symbolic", N_("Keyboard"), KeyboardPage),
    ("audio-volume-high-symbolic", N_("Sound"), SoundPage),
    ("system-shutdown-symbolic", N_("Power & Lock"), PowerLockPage),
    ("preferences-desktop-accessibility-symbolic", N_("Accessibility"), AccessibilityPage),
    ("preferences-system-time-symbolic", N_("Date & Time"), DateTimePage),
    ("system-users-symbolic", N_("Users"), UsersPage),
    ("preferences-desktop-locale-symbolic", N_("Language & Region"), LanguagePage),
    ("application-x-executable-symbolic", N_("Default Apps"), DefaultAppsPage),
    ("help-about-symbolic", N_("About"), AboutPage),
]
