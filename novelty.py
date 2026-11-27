"""Static entertainment receipts with no report or database inputs."""
from i18n import tr

ITEMS = {
    "awoo":"Awoo Permit",
    "pointless":"Certificate of Pointlessness",
    "jank":"Certified Jank",
    "engineer":"Emotional Support Engineer",
}


def render(kind, language):
    title=ITEMS[kind]
    text=tr(language,"SPASSBELEG · OHNE GÜLTIGKEIT")
    disclaimer=tr(language,"Kein Prüfprotokoll oder Nachweis.")
    body=(text+"\n"+"-"*34+"\n"+title+"\n"+"-"*34+"\n"+disclaimer+"\nFMI Printstation\n").encode("cp850")
    return b"\x1b@\x1bt\x02\x1ba\x01"+body+b"\x1bJ\x78\x1dV\x00"
