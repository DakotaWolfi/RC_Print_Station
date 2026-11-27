"""Touch keyboard with the same editing semantics as the physical keyboard."""
from time import monotonic

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QValidator
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton, QSizePolicy, QVBoxLayout, QWidget

ACCENTS = {
    "a": "äàáâãå", "c": "ç", "e": "éèêë", "i": "ïíìî", "n": "ñ",
    "o": "öóòôõ", "s": "ß", "u": "üúùû", "y": "ÿ", "z": "ž",
}
SYMBOLS = ("1234567890", "@#%&*()_-+", "€!?/.:,;'")
MORE = ("[]{}<>^~|=", "£$¥°§©®±÷×", '\\"?;:_-+.')

class AddressValidator(QValidator):
    def validate(self, value, position):
        fields = value.split(".")
        valid = len(fields) <= 4 and all(
            not field or field.isascii() and field.isdecimal() and len(field) <= 3 and int(field) <= 255
            for field in fields
        )
        state = self.Invalid if not valid else self.Acceptable if len(fields) == 4 and all(fields) else self.Intermediate
        return state, value, position


class Keyboard(QWidget):
    finished=pyqtSignal(int)
    def __init__(self, parent, title, value, limit, secret=False, mode="text", *, embedded=False):
        super().__init__(parent,Qt.Widget if embedded else Qt.Dialog)
        self.embedded=embedded
        self.code=0
        self.setWindowTitle(title)
        self.setObjectName("touchKeyboard")
        self.setStyleSheet(parent.styleSheet())
        self.t = parent.t
        self.mode = mode
        self.layer = 0
        self.upper = False
        self.caps = False
        self.shift_at = 0.0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 10)
        title_label = QLabel(title)
        title_label.setProperty("section", True)
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        entry = QHBoxLayout()
        self.edit = QLineEdit(value)
        self.edit.setMaxLength(limit)
        self.edit.setAccessibleName(title)
        if secret:
            self.edit.setEchoMode(QLineEdit.Password)
        if mode == "ipv4":
            self.edit.setValidator(AddressValidator(self.edit))
        self.edit.selectAll()
        entry.addWidget(self.edit, 1)
        for text, name, callback in (
                ("←", "Cursor links", lambda: self.edit.cursorBackward(False)),
                ("→", "Cursor rechts", lambda: self.edit.cursorForward(False))):
            key = self.key(text, callback)
            key.setAccessibleName(self.t(name))
            key.setFixedSize(49,48)
            key.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            entry.addWidget(key)
        if secret:
            eye = self.key(self.t("Anzeigen"), self.toggle_password)
            eye.setCheckable(True)
            eye.setFixedSize(100,48)
            eye.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            self.eye = eye
            entry.addWidget(eye)
        layout.addLayout(entry)
        self.accents=QHBoxLayout()
        self.accent_row=QWidget()
        self.accent_row.setLayout(self.accents)
        self.accent_row.hide()
        layout.addWidget(self.accent_row)
        self.grid = QGridLayout()
        self.grid.setSpacing(2)
        layout.addLayout(self.grid, 1)
        actions = QHBoxLayout()
        cancel=self.key(self.t("Abbrechen"), self.reject)
        cancel.setMinimumHeight(48)
        actions.addWidget(cancel)
        self.done_button = self.key(self.t("Übernehmen"), self.accept)
        self.done_button.setProperty("primary", True)
        self.done_button.setMinimumHeight(48)
        actions.addWidget(self.done_button)
        layout.addLayout(actions)
        self.edit.returnPressed.connect(self.accept)
        self.edit.textChanged.connect(self.validate)
        self.rebuild()
        self.validate()
        self.edit.setFocus()
        if not embedded:
            self.resize(min(parent.width() - 4, 1000), parent.height() - 12)

    def validate(self):
        acceptable = self.edit.hasAcceptableInput() and (self.mode != "number" or self.edit.text().isascii()
                    and self.edit.text().isdecimal())
        self.done_button.setEnabled(acceptable)

    def result(self):
        return self.code

    def finish(self,code):
        self.code=code
        self.hide()
        self.finished.emit(code)

    def accept(self):
        if self.done_button.isEnabled():
            self.finish(1)

    def reject(self):
        self.finish(0)

    def toggle_password(self):
        visible = self.eye.isChecked()
        self.edit.setEchoMode(QLineEdit.Normal if visible else QLineEdit.Password)
        self.eye.setText(self.t("Verbergen" if visible else "Anzeigen"))

    def key(self, text, action):
        key = QPushButton(text)
        key.setAccessibleName(text)
        key.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        key.setFocusPolicy(Qt.NoFocus)
        key.setAutoDefault(False)
        key.setStyleSheet("padding: 2px; min-width: 0; min-height: 40px; font-size: 17px;")
        key.clicked.connect(lambda _checked=False:action())
        return key

    def char(self, value):
        self.edit.insert(value)
        if self.upper and not self.caps and not self.layer:
            self.upper = False
            self.update_cases()

    def shift(self):
        now = monotonic()
        if self.caps:
            self.upper = self.caps = False
        elif now-self.shift_at<.36:
            self.upper = self.caps = True
        else:
            self.upper = not self.upper
        self.shift_at = now
        self.update_cases()

    def update_cases(self):
        self.shift_key.setText("⇪" if self.caps else "⬆" if self.upper else "⇧")
        for key in self.letters:
            raw = key.property("letter")
            key.setText(raw.upper() if self.upper else raw)

    def change(self, layer):
        self.layer = layer
        self.rebuild()

    def add_letter(self, letter, row, col, span):
        key = self.key(letter.upper() if self.upper and not self.layer else letter,
                       lambda: self.char(key.text()))
        if self.embedded and not self.layer and letter in ACCENTS:
            timer=QTimer(key,singleShot=True,interval=450)
            key.pressed.connect(timer.start)
            key.released.connect(timer.stop)
            timer.timeout.connect(lambda:self.show_accents(key,letter))
        elif not self.layer and letter in ACCENTS:
            popup = QMenu(key)
            popup.setStyleSheet("QMenu::item {padding: 10px 20px;}")
            for raw in ACCENTS[letter]:
                popup.addAction(raw, lambda _=False, a=raw: self.char(a.upper() if self.upper else a))
            # Long press opens variants. Suppress the normal click when the
            # release follows a popup gesture.
            timer = QTimer(key, singleShot=True, interval=450)
            key.pressed.connect(timer.start)
            key.released.connect(timer.stop)
            def open_accents():
                key.setDown(False)
                for action, raw in zip(popup.actions(), ACCENTS[letter]):
                    action.setText(raw.upper() if self.upper else raw)
                popup.popup(key.mapToGlobal(key.rect().bottomLeft()))
            timer.timeout.connect(open_accents)
        if not self.layer:
            key.setProperty("letter", letter)
            self.letters.append(key)
        self.grid.addWidget(key, row, col, 1, span)

    def show_accents(self,key,letter):
        key.setDown(False)
        while self.accents.count():
            item=self.accents.takeAt(0).widget()
            item.deleteLater()
        def pick(value):
            if value:
                self.char(value)
            self.accent_row.hide()
        for raw in ACCENTS[letter]:
            value=raw.upper() if self.upper else raw
            self.accents.addWidget(self.key(value,lambda value=value:pick(value)))
        self.accents.addWidget(self.key("×",lambda:pick("")))
        self.accent_row.show()

    def erase(self):
        key = self.key("⌫", self.edit.backspace)
        key.setAccessibleName(self.t("Zeichen löschen"))
        key.setAutoRepeat(True)
        key.setAutoRepeatDelay(470)
        key.setAutoRepeatInterval(65)
        return key

    def rebuild(self):
        while self.grid.count():
            item = self.grid.takeAt(0).widget()
            item.hide()
            item.deleteLater()
        self.letters = []
        if self.mode in ("number", "ipv4", "ticket") and self.layer == 0:
            for index, digit in enumerate("123456789"):
                self.grid.addWidget(self.key(digit, lambda _, digit=digit: self.char(digit)), index//3, index%3)
            if self.mode == "ipv4":
                self.grid.addWidget(self.key(".", lambda: self.char(".")), 3, 0)
            elif self.mode == "ticket":
                self.grid.addWidget(self.key("ABC", lambda: self.change(1)), 3, 0)
            self.grid.addWidget(self.key("0", lambda: self.char("0")), 3, 1)
            self.grid.addWidget(self.erase(), 3, 2)
            return
        symbols = self.layer if self.mode != "ticket" else self.layer - 1
        saved = self.layer
        self.layer = symbols
        rows = (MORE if symbols == 2 else SYMBOLS) if symbols else (
            "qwertyuiop" if self.parent().state.get("language") == "en" else "qwertzuiop",
            "asdfghjkl", "zxcvbnm" if self.parent().state.get("language") == "en" else "yxcvbnm")
        for n, row in enumerate(rows):
            offset = (20 - len(row) * 2) // 2
            for i, value in enumerate(row):
                self.add_letter(value, n, offset + i*2, 2)
        self.layer = saved
        if symbols:
            first = self.key("ABC", lambda: self.change(1 if self.mode == "ticket" else 0))
        else:
            first = self.shift_key = self.key("⇧", self.shift)
            self.update_cases()
            first.setAccessibleName(self.t("Grossschreibung"))
        offset = int(self.mode == "ticket")
        self.grid.addWidget(first, 3, 0, 1, 3)
        label = "123" if not symbols else ("#+=" if symbols == 1 else "123")
        self.grid.addWidget(self.key(label, lambda: self.change(offset + (2 if symbols == 1 else 1))), 3, 3, 1, 3)
        self.grid.addWidget(self.key(self.t("Leerzeichen"), lambda: self.char(" ")), 3, 6, 1, 9)
        self.grid.addWidget(self.erase(), 3, 15, 1, 5)
