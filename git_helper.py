#!/usr/bin/env python3
"""Git Helper - everyday Git tasks in plain language, for non-technical users."""

import atexit
import os
import re
import shlex
import shutil
import sys
import tempfile
from datetime import datetime
from string import Template

from PyQt6.QtCore import (
    QObject, QProcess, QProcessEnvironment, QSettings, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFontMetrics, QIcon
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QGridLayout, QSizePolicy, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QTabWidget,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

APP_ID = "git-helper"
APP_TITLE = "Barsha's Git Helper"

# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------

LIGHT = dict(
    bg="#f4f6fa", card="#ffffff", text="#1f2937", muted="#6b7280", border="#e3e7ef",
    accent="#4f6df5", accent_text="#ffffff", hover="#eef1ff",
    ok_bg="#e6f6ec", ok_fg="#176a3a", err_bg="#fdecec", err_fg="#a12626",
    info_bg="#eaf0ff", info_fg="#2f4bc4",
)
DARK = dict(
    bg="#14161c", card="#1d2029", text="#e6e8ee", muted="#9aa1b2", border="#2a2e3a",
    accent="#7b93ff", accent_text="#10131c", hover="#262b3b",
    ok_bg="#173326", ok_fg="#7be0a0", err_bg="#3a1c1f", err_fg="#ff9b9b",
    info_bg="#1f2a4d", info_fg="#a9baff",
)

QSS = Template("""
* { font-family: "Inter", "Noto Sans", "Ubuntu", "Cantarell", sans-serif; font-size: 13px; }
QWidget { color: $text; }
QMainWindow, QDialog, QMessageBox, QInputDialog, QWidget#root { background: $bg; }
QLabel { background: transparent; }
QFrame#card { background: $card; border: 1px solid $border; border-radius: 12px; }
QLabel#h1 { font-size: 20px; font-weight: 700; }
QLabel#muted { color: $muted; }
QLabel#section { color: $muted; font-size: 11px; font-weight: 700; padding-top: 8px; }
QLabel#chip { background: $hover; color: $accent; border-radius: 10px; padding: 3px 10px; font-weight: 600; }
QLabel#banner { padding: 6px 16px; border-radius: 10px; font-size: 13px; }
QLabel#banner[kind="ok"] { background: $ok_bg; color: $ok_fg; }
QLabel#banner[kind="error"] { background: $err_bg; color: $err_fg; }
QLabel#banner[kind="info"] { background: $info_bg; color: $info_fg; }
QPushButton { background: $card; border: 1px solid $border; border-radius: 8px; padding: 7px 16px; }
QPushButton:hover { border-color: $accent; }
QPushButton:disabled { color: $muted; }
QPushButton#action { text-align: left; padding: 0; border: none; border-radius: 12px; }
QLabel#actionTitle { color: #ffffff; font-size: 14px; font-weight: 700; }
QLabel#actionSub { color: rgba(255, 255, 255, 0.9); font-size: 13px; }
QLabel#actionTitle:disabled, QLabel#actionSub:disabled { color: $muted; }
QTreeWidget, QPlainTextEdit, QLineEdit {
    background: $card; border: 1px solid $border; border-radius: 10px; padding: 6px;
    selection-background-color: $hover; selection-color: $text;
}
QTreeWidget::item { padding: 6px 4px; }
QTreeWidget::item:selected { background: $hover; color: $text; }
QHeaderView::section { background: $card; color: $muted; border: none; border-bottom: 1px solid $border; padding: 6px; font-weight: 600; }
QTabWidget::pane { border: none; top: -1px; }
QTabBar::tab { background: transparent; color: $muted; padding: 8px 16px; margin-right: 4px; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:selected { color: $accent; border-bottom: 2px solid $accent; }
QProgressBar { background: $border; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }
QProgressBar::chunk { background: $accent; border-radius: 2px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: $border; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox::indicator, QTreeWidget::indicator { width: 16px; height: 16px; border: 2px solid $muted; border-radius: 5px; background: $card; }
QCheckBox::indicator:hover, QTreeWidget::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked, QTreeWidget::indicator:checked { background: $accent; border-color: $accent; }
QToolTip { background: $card; color: $text; border: 1px solid $border; padding: 4px; }
""")


def is_dark(app):
    try:
        if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
            return True
    except Exception:
        pass
    return app.palette().window().color().lightness() < 128


TONES = {
    "blue": "#2f6fed", "teal": "#0b8a86", "orange": "#c46200", "green": "#1f8f4e",
    "indigo": "#4f46e5", "purple": "#7c3aed", "pink": "#c2338a", "slate": "#586175",
    "gold": "#8f6b00", "red": "#d13b3b",
}


def tone_qss(border):
    rules = []
    for name, color in TONES.items():
        light = QColor(color).lighter(115).name()
        rules.append('QPushButton#action[tone="%s"] { background: %s; }' % (name, color))
        rules.append('QPushButton#action[tone="%s"]:hover { background: %s; }' % (name, light))
        rules.append('QPushButton#action[tone="%s"]:disabled { background: %s; }' % (name, border))
    return "\n".join(rules)


def apply_theme(app):
    app.setStyle("Fusion")
    pal = DARK if is_dark(app) else LIGHT
    app.setStyleSheet(QSS.substitute(pal) + tone_qss(pal["border"]))


def resource_path(rel):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# --------------------------------------------------------------------------
# SSH password support
#
# ssh runs the "askpass" program whenever it needs a key password. We point it
# at a tiny wrapper that re-launches this app in --askpass mode, which shows a
# normal password dialog. AddKeysToAgent lets ssh remember the key afterwards
# (when an ssh-agent is running) so the password is only asked once.
# --------------------------------------------------------------------------

_ASKPASS_PATH = None


def make_askpass_wrapper():
    global _ASKPASS_PATH
    folder = tempfile.mkdtemp(prefix="git-helper-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
    atexit.register(shutil.rmtree, folder, True)
    path = os.path.join(folder, "askpass.sh")
    cmd = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
    with open(path, "w") as fh:
        fh.write('#!/bin/sh\nexec %s --askpass "$@"\n' % " ".join(shlex.quote(c) for c in cmd))
    os.chmod(path, 0o700)
    _ASKPASS_PATH = path


def run_askpass(prompt):
    """Entry point used by ssh. Prints the answer on stdout; exit code 1 means cancelled."""
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(resource_path("assets/icon.png")))
    apply_theme(app)
    if "(yes/no" in prompt:
        reply = QMessageBox.question(None, "Confirm connection", prompt)
        answer, ok = ("yes" if reply == QMessageBox.StandardButton.Yes else "no"), True
    else:
        answer, ok = QInputDialog.getText(
            None, "Password needed",
            "Your security key is protected by a password.\nPlease enter it to continue.\n\n" + prompt,
            QLineEdit.EchoMode.Password,
        )
    if ok:
        sys.stdout.write(answer + "\n")
        sys.stdout.flush()
        sys.exit(0)
    sys.exit(1)


# --------------------------------------------------------------------------
# Git runner (asynchronous, one command at a time, queued)
# --------------------------------------------------------------------------

class Git(QObject):
    busy = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.repo = None
        self.proc = None
        self.queue = []
        self._dispatching = False

    def _env(self, network):
        env = QProcessEnvironment.systemEnvironment()
        # PyInstaller points LD_LIBRARY_PATH at its own bundled libraries; git and
        # ssh must use the system ones instead.
        if env.contains("LD_LIBRARY_PATH_ORIG"):
            env.insert("LD_LIBRARY_PATH", env.value("LD_LIBRARY_PATH_ORIG"))
        else:
            env.remove("LD_LIBRARY_PATH")
        env.insert("LC_ALL", "C.UTF-8")
        env.insert("GIT_TERMINAL_PROMPT", "0")
        if network and _ASKPASS_PATH:
            env.insert("SSH_ASKPASS", _ASKPASS_PATH)
            env.insert("SSH_ASKPASS_REQUIRE", "force")
            env.insert(
                "GIT_SSH_COMMAND",
                "ssh -o StrictHostKeyChecking=accept-new -o AddKeysToAgent=yes -o ConnectTimeout=20",
            )
        return env

    def run(self, args, done, network=False):
        self.queue.append((args, done, network))
        if self.proc is None and not self._dispatching:
            self._next()

    def _next(self):
        if not self.queue:
            self.busy.emit(False)
            return
        args, done, network = self.queue.pop(0)
        p = QProcess(self)
        self.proc = p
        p.setWorkingDirectory(self.repo or os.path.expanduser("~"))
        p.setProcessEnvironment(self._env(network))
        p.finished.connect(lambda code, _s, p=p, d=done: self._finish(p, d, code))
        p.errorOccurred.connect(lambda err, p=p, d=done: self._failed(p, d, err))
        self.busy.emit(True)
        p.start("git", args)

    def _failed(self, p, done, err):
        if err == QProcess.ProcessError.FailedToStart:
            self._finish(p, done, -1, "Git is not installed on this computer.")

    def _finish(self, p, done, code, forced_err=None):
        if self.proc is not p:
            return
        out = bytes(p.readAllStandardOutput()).decode("utf-8", "replace")
        err = forced_err or bytes(p.readAllStandardError()).decode("utf-8", "replace")
        self.proc = None
        p.deleteLater()
        self._dispatching = True
        try:
            done(code, out, err)
        finally:
            self._dispatching = False
            self._next()


FRIENDLY = [
    ("git is not installed", "Git is not installed on this computer."),
    ("permission denied (publickey)", "The server did not accept your security key. Check that the right key is set up and that the password was typed correctly."),
    ("authentication failed", "The server did not accept your sign-in."),
    ("host key verification failed", "The server's identity could not be verified. Ask your administrator for help."),
    ("could not resolve hostname", "Could not reach the server. Please check your internet connection."),
    ("network is unreachable", "Could not reach the server. Please check your internet connection."),
    ("timed out", "The server took too long to answer. Please check your internet connection and try again."),
    ("connection refused", "The server refused the connection. Please try again later."),
    ("would be overwritten", "Your unsaved changes would be overwritten. Save them (Add files, then Save changes) or set them aside first."),
    ("conflict", "Some online updates overlap with your own changes and could not be combined automatically. Nothing was changed. Please ask for help."),
    ("non-fast-forward", "Someone else has uploaded newer changes. Download updates first, then upload again."),
    ("fetch first", "Someone else has uploaded newer changes. Download updates first, then upload again."),
    ("[rejected]", "The server did not accept the upload. Download updates first, then try again."),
    ("tracking information", "This project is not linked to an online copy yet. Use Upload changes to link it."),
    ("nothing to commit", "There is nothing new to save."),
    ("no local changes to save", "There are no changes to set aside."),
    ("no stash entries", "There are no set-aside changes to bring back."),
    ("not a git repository", "That folder is not a Git project."),
]


def friendly(text):
    low = text.lower()
    for key, msg in FRIENDLY:
        if key in low:
            return msg
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "Something went wrong: " + (lines[-1] if lines else "unknown error")


# --------------------------------------------------------------------------
# UI pieces
# --------------------------------------------------------------------------

class ActionButton(QPushButton):
    def __init__(self, title, subtitle, tone):
        super().__init__()
        self.setObjectName("action")
        self.setProperty("tone", tone)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(78)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("actionTitle")
        s = QLabel(subtitle)
        s.setObjectName("actionSub")
        s.setWordWrap(True)
        s.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        for w in (t, s):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay.addWidget(w)
        lay.addStretch(1)


ACTIONS = [
    ("GET UPDATES", [
        ("fetch", "Check for updates", "Fetch: see if there are updates available", "blue"),
        ("pull", "Download updates", "Pull: bring online changes here", "teal"),
    ]),
    ("SAVE YOUR WORK", [
        ("add", "Add files", "Add: pick files for your next save", "orange"),
        ("commit", "Save changes", "Commit: save added files with a note", "green"),
        ("push", "Upload changes", "Push: send your saved work online", "indigo"),
    ]),
    ("SET WORK ASIDE", [
        ("stash", "Set changes aside", "Stash: put changes away for now", "purple"),
        ("pop", "Bring changes back", "Restore: get set-aside changes", "pink"),
    ]),
    ("MORE", [
        ("status", "Refresh status", "Status: see what has changed", "slate"),
        ("unadd", "Undo add", "Take ticked files off the list", "gold"),
        ("discard", "Throw away", "Permanently undo ticked files", "red"),
    ]),
]


def describe(x, y):
    if x == "?":
        return "New file"
    if "U" in (x, y) or (x, y) in (("A", "A"), ("D", "D")):
        return "Conflict"
    code = x if x != " " else y
    return {"M": "Changed", "A": "New file", "D": "Deleted", "R": "Renamed",
            "C": "Copied", "T": "Type changed"}.get(code, "Changed")


def stage_state(x, y):
    if describe(x, y) == "Conflict":
        return "Needs attention"
    if x in " ?":
        return "Not added yet"
    return "Ready to save" if y == " " else "Partly added"


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setFixedSize(1000, 690)
        self.settings = QSettings("GitHelper", APP_ID)
        self.git = Git(self)
        self.git.busy.connect(self.set_busy)
        self.files = []          # (x, y, path)
        self.state = {}
        self.stash_count = 0
        self.is_busy = False
        self.buttons = {}
        self._build_ui()

        handlers = {
            "fetch": self.do_fetch, "pull": self.do_pull, "add": self.do_add,
            "commit": self.do_commit, "push": self.do_push, "stash": self.do_stash,
            "pop": self.do_pop, "status": self.do_status, "unadd": self.do_unadd,
            "discard": self.do_discard,
        }
        for key, fn in handlers.items():
            self.buttons[key].clicked.connect(fn)

        self.timer = QTimer(self)
        self.timer.setInterval(20000)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.set_busy(False)

        saved = self.settings.value("repo", "")
        if saved and os.path.isdir(saved):
            self.open_repo(saved)
        else:
            QTimer.singleShot(250, self.choose_repo)

    # ---- layout ----------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(20, 14, 20, 14)
        outer.setSpacing(10)

        head = QFrame()
        head.setObjectName("card")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(18, 14, 18, 14)
        names = QVBoxLayout()
        names.setSpacing(2)
        self.repo_name = QLabel("No project chosen")
        self.repo_name.setObjectName("h1")
        self.repo_path = QLabel("Choose the folder you want to work with.")
        self.repo_path.setObjectName("muted")
        self.repo_path.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        names.addWidget(self.repo_name)
        names.addWidget(self.repo_path)
        hl.addLayout(names, 1)
        self.branch_chip = QLabel("")
        self.branch_chip.setObjectName("chip")
        self.branch_chip.setVisible(False)
        self.sync_label = QLabel("")
        self.sync_label.setObjectName("muted")
        hl.addWidget(self.branch_chip)
        hl.addSpacing(8)
        hl.addWidget(self.sync_label)
        hl.addSpacing(16)
        choose = QPushButton("Choose folder...")
        choose.clicked.connect(self.choose_repo)
        hl.addWidget(choose)
        self.choose_btn = choose
        outer.addWidget(head)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(4)
        outer.addWidget(self.progress)

        self.banner_label = QLabel("")
        self.banner_label.setObjectName("banner")
        self.banner_label.setWordWrap(True)
        self.banner_label.setFixedHeight(54)
        outer.addWidget(self.banner_label)
        self.banner("Welcome. Choose your project folder to get started.", "info")

        body = QHBoxLayout()
        body.setSpacing(16)
        outer.addLayout(body, 1)

        # left: coloured actions in a 3-column grid
        side = QWidget()
        grid = QGridLayout(side)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        row = 0
        for heading, items in ACTIONS:
            lab = QLabel(heading)
            lab.setObjectName("section")
            grid.addWidget(lab, row, 0, 1, 3)
            row += 1
            for col, (key, title, sub, tone) in enumerate(items):
                b = ActionButton(title, sub, tone)
                self.buttons[key] = b
                grid.addWidget(b, row, col)
            row += 1
        for c in range(3):
            grid.setColumnStretch(c, 1)
        # grid.setRowStretch(row, 1)
        side.setFixedWidth(500)
        side.setFixedHeight(500)
        body.addWidget(side)

        # right: tabs
        self.tabs = QTabWidget()
        body.addWidget(self.tabs, 1)

        changes = QWidget()
        cl = QVBoxLayout(changes)
        cl.setContentsMargins(0, 10, 0, 0)
        cl.setSpacing(8)
        top = QHBoxLayout()
        self.tick_all = QCheckBox("Tick all files")
        self.tick_all.toggled.connect(self.on_tick_all)
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        top.addWidget(self.tick_all)
        top.addStretch(1)
        top.addWidget(self.count_label)
        cl.addLayout(top)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["File", "What happened", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.setColumnWidth(0, 150)
        self.tree.setColumnWidth(1, 150)
        cl.addWidget(self.tree, 1)
        note_label = QLabel("Note for your next save (required):")
        note_label.setObjectName("muted")
        cl.addWidget(note_label)
        self.note = QPlainTextEdit()
        self.note.setPlaceholderText("Describe what you changed, for example: Updated the price list")
        self.note.setFixedHeight(76)
        cl.addWidget(self.note)
        self.tabs.addTab(changes, "Changes")

        self.history = QTreeWidget()
        self.history.setHeaderLabels(["When", "Who", "What was saved"])
        self.history.setRootIsDecorated(False)
        self.history.setColumnWidth(0, 130)
        self.history.setColumnWidth(1, 150)
        self.tabs.addTab(self.history, "History")

        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.tabs.addTab(self.logbox, "Details")

    # ---- small helpers ---------------------------------------------------

    def banner(self, text, kind="info"):
        self.banner_label.setText(text)
        self.banner_label.setProperty("kind", kind)
        self.banner_label.style().unpolish(self.banner_label)
        self.banner_label.style().polish(self.banner_label)
        self.banner_label.setVisible(True)

    def log(self, title, text, code=0):
        stamp = datetime.now().strftime("%H:%M:%S")
        status = "ok" if code == 0 else "failed"
        self.logbox.appendPlainText("[%s] %s (%s)\n%s\n" % (stamp, title, status, text.strip()))

    def set_busy(self, busy):
        self.is_busy = busy
        self.progress.setRange(0, 0 if busy else 1)
        self.progress.setValue(0)
        ready = (not busy) and self.git.repo is not None
        for b in self.buttons.values():
            b.setEnabled(ready)
        self.choose_btn.setEnabled(not busy)

    def checked_files(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.checkState(0) == Qt.CheckState.Checked:
                out.append(it.data(0, Qt.ItemDataRole.UserRole))
        return out

    def on_tick_all(self, on):
        state = Qt.CheckState.Checked if on else Qt.CheckState.Unchecked
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, state)

    # ---- repository ------------------------------------------------------

    def choose_repo(self):
        start = self.git.repo or os.path.expanduser("~")
        folder = QFileDialog.getExistingDirectory(self, "Choose your project folder", start)
        if folder:
            self.open_repo(folder)

    def open_repo(self, path):
        previous = self.git.repo
        self.git.repo = path

        def done(code, out, err):
            if code != 0:
                self.git.repo = previous
                self.banner("That folder is not a Git project. Please choose a different folder.", "error")
                self.set_busy(False)
                return
            top = out.strip()
            self.git.repo = top
            self.settings.setValue("repo", top)
            self.repo_name.setText(os.path.basename(top) or top)
            self.repo_path.setText(
                QFontMetrics(self.repo_path.font()).elidedText(top, Qt.TextElideMode.ElideMiddle, 520))
            self.repo_path.setToolTip(top)
            self.banner("Project loaded. Pick an action on the left.", "info")
            self.refresh()

        self.git.run(["rev-parse", "--show-toplevel"], done)

    def refresh(self):
        if not self.git.repo:
            return

        def got_status(code, out, err):
            if code != 0:
                self.banner(friendly(out + err), "error")
                return
            self.parse_status(out)
            self.git.run(["stash", "list"], got_stash)

        def got_stash(code, out, err):
            self.stash_count = len([l for l in out.splitlines() if l.strip()]) if code == 0 else 0
            self.update_header()
            self.git.run(
                ["log", "-n", "100", "--pretty=format:%ar%x1f%an%x1f%s"], got_log)

        def got_log(code, out, err):
            self.history.clear()
            if code == 0:
                for line in out.splitlines():
                    parts = line.split("\x1f")
                    if len(parts) == 3:
                        self.history.addTopLevelItem(QTreeWidgetItem(parts))

        self.git.run(["--no-optional-locks", "status", "--porcelain=v1", "-b", "-z"], got_status)

    def parse_status(self, out):
        parts = out.split("\0")
        header = parts[0][3:] if parts and parts[0].startswith("## ") else ""
        info = dict(branch=header, upstream=None, ahead=0, behind=0)
        m = re.match(r"(.+?)\.\.\.(\S+)(?: \[(.*)\])?$", header)
        if m:
            info["branch"], info["upstream"] = m.group(1), m.group(2)
            extra = m.group(3) or ""
            a, b = re.search(r"ahead (\d+)", extra), re.search(r"behind (\d+)", extra)
            info["ahead"] = int(a.group(1)) if a else 0
            info["behind"] = int(b.group(1)) if b else 0
        elif header.startswith("No commits yet on "):
            info["branch"] = header[len("No commits yet on "):]
        elif header.startswith("HEAD (no branch)"):
            info["branch"] = "detached"
        self.state = info

        files, i = [], 1
        while i < len(parts):
            ent = parts[i]
            i += 1
            if len(ent) < 4:
                continue
            x, y, path = ent[0], ent[1], ent[3:]
            if x in "RC":
                i += 1  # skip the original name
            files.append((x, y, path))
        self.files = files

        keep = {p for _x, _y, p in self.checked_files()}
        self.tree.clear()
        for x, y, path in files:
            it = QTreeWidgetItem([path, describe(x, y), stage_state(x, y)])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked if path in keep else Qt.CheckState.Unchecked)
            it.setData(0, Qt.ItemDataRole.UserRole, (x, y, path))
            self.tree.addTopLevelItem(it)
        self.tick_all.blockSignals(True)
        self.tick_all.setChecked(False)
        self.tick_all.blockSignals(False)
        n = len(files)
        self.count_label.setText("No changed files" if n == 0 else "%d changed file%s" % (n, "" if n == 1 else "s"))

    def update_header(self):
        s = self.state
        self.branch_chip.setText("Branch: " + s.get("branch", ""))
        self.branch_chip.setVisible(True)
        bits = []
        if not s.get("upstream"):
            bits.append("Not yet uploaded")
        else:
            if s["ahead"]:
                bits.append("%d to upload" % s["ahead"])
            if s["behind"]:
                bits.append("%d update%s to download" % (s["behind"], "" if s["behind"] == 1 else "s"))
            if not s["ahead"] and not s["behind"]:
                bits.append("Up to date")
        if self.stash_count:
            bits.append("%d set aside" % self.stash_count)
        self.sync_label.setText("  |  ".join(bits))

    # ---- generic command with friendly result ----------------------------

    def simple(self, title, args, ok_msg, network=False):
        def done(code, out, err):
            text = (out + "\n" + err).strip()
            self.log(title, text, code)
            if code == 0:
                self.banner(ok_msg(text) if callable(ok_msg) else ok_msg, "ok")
            else:
                self.banner(friendly(text), "error")
            self.refresh()
        self.git.run(args, done, network)

    # ---- actions ---------------------------------------------------------

    def do_status(self):
        self.banner("Status refreshed.", "ok")
        self.refresh()

    def do_fetch(self):
        self.simple("Check for updates (fetch)", ["fetch", "--prune"],
                    "Checked the server. See the summary at the top of the window.", network=True)

    def do_pull(self):
        def done(code, out, err):
            text = (out + "\n" + err).strip()
            self.log("Download updates (pull)", text, code)
            if code == 0:
                up = "already up to date" in text.lower()
                self.banner("Already up to date." if up else "Updates downloaded.", "ok")
            else:
                if "conflict" in text.lower():
                    self.git.run(["merge", "--abort"], lambda *_: None)
                self.banner(friendly(text), "error")
            self.refresh()
        self.git.run(["pull", "--no-rebase", "--no-edit"], done, True)

    def do_add(self):
        if not self.files:
            self.banner("There are no changed files to add.", "info")
            return
        paths = [p for _x, _y, p in self.checked_files()]
        args = ["add", "-A", "--"] + paths if paths else ["add", "-A"]
        what = "The ticked files were added." if paths else "All changed files were added."
        self.simple("Add files", args, what + " Now write a note and press Save changes.")

    def do_unadd(self):
        sel = [p for x, _y, p in self.checked_files() if x not in " ?"]
        if not sel:
            self.banner("Tick the files you want to remove from your next save first.", "info")
            return
        self.simple("Undo add", ["restore", "--staged", "--"] + sel, "The ticked files will not be part of your next save.")

    def do_commit(self):
        staged = [f for f in self.files if f[0] not in " ?"]
        msg = self.note.toPlainText().strip()
        if not staged:
            self.banner("Nothing is ready to save yet. Use Add files first.", "info")
            return
        if not msg:
            self.banner("Please type a short note describing your changes.", "info")
            self.note.setFocus()
            return

        def attempt():
            def done(code, out, err):
                text = (out + "\n" + err).strip()
                self.log("Save changes (commit)", text, code)
                low = text.lower()
                if code == 0:
                    self.note.clear()
                    self.banner("Your changes were saved. Press Upload changes to send them online.", "ok")
                elif "tell me who you are" in low or "empty ident" in low or "unable to auto-detect" in low:
                    ident = self.ask_identity()
                    if ident:
                        name, email = ident
                        self.git.run(["config", "--global", "user.name", name], lambda *_: None)
                        self.git.run(["config", "--global", "user.email", email], lambda *_: attempt())
                        return
                    self.banner("Saving was cancelled because no name was given.", "info")
                else:
                    self.banner(friendly(text), "error")
                self.refresh()
            self.git.run(["commit", "-m", msg], done)

        attempt()

    def ask_identity(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Who are you?")
        form = QFormLayout(dlg)
        form.addRow(QLabel("Your name and email are attached to your saved changes.\nThis is only asked once."))
        name, email = QLineEdit(), QLineEdit()
        form.addRow("Your name", name)
        form.addRow("Your email", email)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() and name.text().strip() and email.text().strip():
            return name.text().strip(), email.text().strip()
        return None

    def do_push(self):
        args = ["push"] if self.state.get("upstream") else ["push", "-u", "origin", "HEAD"]
        self.simple(
            "Upload changes (push)", args,
            lambda t: "Nothing new to upload." if "up-to-date" in t.lower() else "Your changes were uploaded.",
            network=True)

    def do_stash(self):
        if not self.files:
            self.banner("There are no changes to set aside.", "info")
            return
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.simple("Set changes aside (stash)",
                    ["stash", "push", "--include-untracked", "-m", "Set aside with Git Helper on " + stamp],
                    "Your changes were set aside. Your files are back to how they were at the last save.")

    def do_pop(self):
        if self.stash_count == 0:
            self.banner("There are no set-aside changes to bring back.", "info")
            return
        self.simple("Bring changes back (stash pop)", ["stash", "pop"], "Your set-aside changes are back.")

    def do_discard(self):
        sel = self.checked_files()
        if not sel:
            self.banner("Tick the files you want to throw away changes for first.", "info")
            return
        answer = QMessageBox.warning(
            self, "Throw away changes",
            "This will permanently undo your changes to %d file%s.\n\nThis cannot be undone. Continue?"
            % (len(sel), "" if len(sel) == 1 else "s"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        tracked = [p for x, _y, p in sel if x != "?"]
        new = [p for x, _y, p in sel if x == "?"]

        def finish(code=0, out="", err=""):
            self.log("Throw away changes", out + err, code)
            self.banner("The selected changes were thrown away.", "ok")
            self.refresh()

        def clean_new(code, out, err):
            if new:
                self.git.run(["clean", "-fd", "--"] + new, finish)
            else:
                finish(code, out, err)

        if tracked:
            self.git.run(["restore", "--source=HEAD", "--staged", "--worktree", "--"] + tracked, clean_new)
        else:
            clean_new(0, "", "")


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--askpass":
        run_askpass(sys.argv[2] if len(sys.argv) > 2 else "Password:")

    app = QApplication(sys.argv)
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_TITLE)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(resource_path("assets/icon.png")))
    apply_theme(app)
    make_askpass_wrapper()
    win = Main()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()