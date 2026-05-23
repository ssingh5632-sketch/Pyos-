#!/usr/bin/env python3
"""
PyOS - A lightweight CLI Operating System for hidden Identity
Run: python3 pyos.py
"""

import os
import sys
import time
import json
import shutil
import hashlib
import platform
import datetime
import readline  # enables arrow-key history
import textwrap
import random
import signal
import re
import base64 as _base64
import fnmatch

# Persistent state file stored next to this script
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pyos_state.json")

# ─────────────────────────────────────────────
#  ANSI COLOR HELPERS
# ─────────────────────────────────────────────
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    BG_DARK = "\033[40m"

def color(text, *codes):
    return "".join(codes) + str(text) + C.RESET

# ─────────────────────────────────────────────
#  VIRTUAL FILE SYSTEM
# ─────────────────────────────────────────────
class VFS:
    """In-memory hierarchical file system."""

    def __init__(self):
        now = self._ts()
        self._tree = {
            "/": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/home": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/home/user": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/etc": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/bin": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/tmp": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/var": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/var/log": {"_type": "dir", "_meta": {"created": now, "modified": now}},
            "/home/user/readme.txt": {
                "_type": "file",
                "_data": "Welcome to PyOS!\nType 'help' for a list of commands.\n",
                "_meta": {"created": now, "modified": now, "size": 48},
            },
            "/etc/motd": {
                "_type": "file",
                "_data": "PyOS 2.0 — Lightweight Python OS Simulator\n",
                "_meta": {"created": now, "modified": now, "size": 43},
            },
            "/var/log/syslog": {
                "_type": "file",
                "_data": f"[{now}] PyOS kernel started.\n",
                "_meta": {"created": now, "modified": now, "size": 40},
            },
        }

    # ── helpers ──────────────────────────────
    @staticmethod
    def _ts():
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _normalize(self, path, cwd="/"):
        if not path.startswith("/"):
            path = cwd.rstrip("/") + "/" + path
        parts = []
        for p in path.split("/"):
            if p == "" or p == ".":
                continue
            elif p == "..":
                if parts:
                    parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts)

    # ── public API ───────────────────────────
    def exists(self, path):
        return path in self._tree

    def is_dir(self, path):
        return self._tree.get(path, {}).get("_type") == "dir"

    def is_file(self, path):
        return self._tree.get(path, {}).get("_type") == "file"

    def listdir(self, path):
        """Return immediate children of a directory."""
        path = path.rstrip("/") if path != "/" else "/"
        children = []
        prefix = path if path == "/" else path + "/"
        for k in self._tree:
            if k == path:
                continue
            if k.startswith(prefix):
                rest = k[len(prefix):]
                if "/" not in rest:
                    children.append(rest)
        return sorted(children)

    def read(self, path):
        node = self._tree.get(path)
        if not node or node["_type"] != "file":
            raise FileNotFoundError(f"No such file: {path}")
        return node["_data"]

    def write(self, path, data, append=False):
        now = self._ts()
        if path in self._tree and self._tree[path]["_type"] == "file":
            if append:
                data = self._tree[path]["_data"] + data
            self._tree[path]["_data"] = data
            self._tree[path]["_meta"]["modified"] = now
            self._tree[path]["_meta"]["size"] = len(data)
        else:
            # ensure parent exists
            parent = "/".join(path.split("/")[:-1]) or "/"
            if not self.is_dir(parent):
                raise FileNotFoundError(f"No such directory: {parent}")
            self._tree[path] = {
                "_type": "file",
                "_data": data,
                "_meta": {"created": now, "modified": now, "size": len(data)},
            }

    def mkdir(self, path):
        if self.exists(path):
            raise FileExistsError(f"Already exists: {path}")
        parent = "/".join(path.split("/")[:-1]) or "/"
        if not self.is_dir(parent):
            raise FileNotFoundError(f"No such directory: {parent}")
        now = self._ts()
        self._tree[path] = {"_type": "dir", "_meta": {"created": now, "modified": now}}

    def remove(self, path, recursive=False):
        if not self.exists(path):
            raise FileNotFoundError(f"No such file or directory: {path}")
        if self.is_dir(path):
            children = [k for k in self._tree if k != path and k.startswith(path + "/")]
            if children and not recursive:
                raise PermissionError(f"Directory not empty (use -r): {path}")
            for c in children:
                del self._tree[c]
        del self._tree[path]

    def copy(self, src, dst):
        if not self.is_file(src):
            raise FileNotFoundError(f"No such file: {src}")
        data = self.read(src)
        self.write(dst, data)

    def move(self, src, dst):
        self.copy(src, dst)
        self.remove(src)

    def meta(self, path):
        return self._tree.get(path, {}).get("_meta", {})

    def resolve(self, path, cwd):
        return self._normalize(path, cwd)

    def log(self, message):
        """Append to syslog."""
        entry = f"[{self._ts()}] {message}\n"
        try:
            self.write("/var/log/syslog", entry, append=True)
        except Exception:
            pass

    def to_dict(self):
        """Serialize VFS to a plain dict for JSON persistence."""
        return self._tree

    def from_dict(self, data):
        """Restore VFS from a plain dict loaded from JSON."""
        self._tree = data


# ─────────────────────────────────────────────
#  PROCESS TABLE
# ─────────────────────────────────────────────
class ProcessTable:
    def __init__(self):
        self._procs = {}
        self._next_pid = 1
        self.add("kernel", "system")
        self.add("init",   "system")
        self.add("shell",  "user")

    def add(self, name, owner="user"):
        pid = self._next_pid
        self._next_pid += 1
        self._procs[pid] = {
            "pid": pid,
            "name": name,
            "owner": owner,
            "started": datetime.datetime.now().strftime("%H:%M:%S"),
            "status": "running",
        }
        return pid

    def kill(self, pid):
        if pid not in self._procs:
            return False
        if self._procs[pid]["owner"] == "system":
            return False  # can't kill system procs
        del self._procs[pid]
        return True

    def list(self):
        return list(self._procs.values())


# ─────────────────────────────────────────────
#  ENVIRONMENT
# ─────────────────────────────────────────────
class Env:
    def __init__(self):
        self._vars = {
            "SHELL": "/bin/pysh",
            "USER":  "user",
            "HOME":  "/home/user",
            "PATH":  "/bin:/usr/bin",
            "OS":    "PyOS",
            "VER":   "1.0",
            "TERM":  "pyterm-256color",
        }

    def get(self, key, default=""):
        return self._vars.get(key, default)

    def set(self, key, value):
        self._vars[key] = value

    def unset(self, key):
        self._vars.pop(key, None)

    def all(self):
        return dict(self._vars)

    def to_dict(self):
        return dict(self._vars)

    def from_dict(self, data):
        self._vars.update(data)


# ─────────────────────────────────────────────
#  HISTORY
# ─────────────────────────────────────────────
class History:
    def __init__(self):
        self._cmds = []

    def add(self, cmd):
        if cmd.strip():
            self._cmds.append(cmd)

    def all(self):
        return self._cmds

    def last(self, n=10):
        return self._cmds[-n:]

    def to_list(self):
        return list(self._cmds)

    def from_list(self, data):
        self._cmds = list(data)


# ─────────────────────────────────────────────
#  SHELL / COMMAND DISPATCHER
# ─────────────────────────────────────────────
class Shell:
    BANNER = r"""
  ____        ___  ____
 |  _ \ _   _/ _ \/ ___|
 | |_) | | | | | | \___ \
 |  __/| |_| | |_| |___) |
 |_|    \__, |\___/|____/
        |___/          v2.0
"""

    def __init__(self):
        self.vfs  = VFS()
        self.env  = Env()
        self.proc = ProcessTable()
        self.hist = History()
        self.cwd  = "/home/user"
        self.running = True
        self._aliases = {}
        self._users   = {"user": {"password": hashlib.sha256(b"").hexdigest(), "home": "/home/user"}}
        self._cron    = []   # list of {"interval": seconds, "cmd": str, "last": float}
        self._notes   = []   # quick notes store
        signal.signal(signal.SIGINT, self._handle_sigint)
        self._load_state()

    # ── persistence ──────────────────────────
    def _save_state(self):
        """Persist VFS, env, aliases, history, users, cron, notes to disk."""
        state = {
            "vfs":     self.vfs.to_dict(),
            "env":     self.env.to_dict(),
            "aliases": self._aliases,
            "history": self.hist.to_list(),
            "cwd":     self.cwd,
            "users":   self._users,
            "cron":    self._cron,
            "notes":   self._notes,
        }
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            return str(e)

    def _load_state(self):
        """Restore state from disk if it exists."""
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            if "vfs"     in state: self.vfs.from_dict(state["vfs"])
            if "env"     in state: self.env.from_dict(state["env"])
            if "aliases" in state: self._aliases = state["aliases"]
            if "history" in state: self.hist.from_list(state["history"])
            if "cwd"     in state: self.cwd = state["cwd"]
            if "users"   in state: self._users = state["users"]
            if "cron"    in state: self._cron = state["cron"]
            if "notes"   in state: self._notes = state["notes"]
        except Exception:
            pass  # corrupt state — start fresh

    # ── prompt ───────────────────────────────
    def _handle_sigint(self, *_):
        print()  # newline after ^C

    def _prompt(self):
        user = self.env.get("USER")
        host = "pyos"
        path = self.cwd.replace(self.env.get("HOME"), "~")
        return (
            color(f"{user}@{host}", C.GREEN, C.BOLD)
            + color(":", C.RESET)
            + color(path, C.CYAN, C.BOLD)
            + color("$ ", C.RESET)
        )

    # ── tokenizer ────────────────────────────
    @staticmethod
    def _tokenize(line):
        """Split on spaces, respecting quoted strings."""
        tokens, buf, in_q, q_char = [], [], False, None
        for ch in line:
            if in_q:
                if ch == q_char:
                    in_q = False
                else:
                    buf.append(ch)
            elif ch in ('"', "'"):
                in_q, q_char = True, ch
            elif ch == " ":
                if buf:
                    tokens.append("".join(buf))
                    buf = []
            else:
                buf.append(ch)
        if buf:
            tokens.append("".join(buf))
        return tokens

    # ── variable expansion ───────────────────
    def _expand(self, token):
        if token.startswith("$"):
            key = token[1:]
            return self.env.get(key, "")
        return token

    # ── pipe / redirect parsing ───────────────
    def _parse_pipeline(self, line):
        """Split line into commands separated by |."""
        return [cmd.strip() for cmd in line.split("|")]

    # ── run a raw line ───────────────────────
    def run_line(self, line):
        line = line.strip()
        if not line or line.startswith("#"):
            return
        self.hist.add(line)

        # alias expansion
        parts = line.split(None, 1)
        if parts[0] in self._aliases:
            line = self._aliases[parts[0]] + (" " + parts[1] if len(parts) > 1 else "")

        # pipeline
        stages = self._parse_pipeline(line)
        output = None
        for stage in stages:
            output = self._run_cmd(stage, piped_input=output)

        if output is not None:
            print(output, end="" if output.endswith("\n") else "\n")

        # auto-save after every command (silent)
        self._save_state()

    def _run_cmd(self, line, piped_input=None):
        tokens = self._tokenize(line)
        if not tokens:
            return None
        tokens = [self._expand(t) for t in tokens]

        # redirect
        redirect_file, redirect_append = None, False
        clean = []
        i = 0
        while i < len(tokens):
            if tokens[i] in (">>", ">") and i + 1 < len(tokens):
                redirect_append = tokens[i] == ">>"
                redirect_file = self.vfs.resolve(tokens[i + 1], self.cwd)
                i += 2
            else:
                clean.append(tokens[i])
                i += 1
        tokens = clean

        cmd, args = tokens[0], tokens[1:]
        method = getattr(self, f"cmd_{cmd}", None)

        # capture stdout to string if piping or redirecting
        if piped_input is not None or redirect_file:
            import io
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                if piped_input is not None and method:
                    # inject piped_input as stdin substitute
                    result = method(args, stdin=piped_input)
                elif method:
                    result = method(args)
                else:
                    result = self._unknown(cmd)
            finally:
                captured = sys.stdout.getvalue()
                sys.stdout = old_stdout
            output = (captured or "") + (result or "")
            if redirect_file:
                try:
                    self.vfs.write(redirect_file, output, append=redirect_append)
                except Exception as e:
                    print(color(f"redirect error: {e}", C.RED))
                return None
            return output
        else:
            if method:
                result = method(args)
            else:
                result = self._unknown(cmd)
            if result:
                print(result, end="" if result.endswith("\n") else "\n")
            return None

    def _unknown(self, cmd):
        return color(f"pysh: command not found: {cmd}  (type 'help')", C.RED)

    # ─────────────────────────────────────────
    #  COMMANDS
    # ─────────────────────────────────────────

    def cmd_help(self, args, **_):
        cols = {
            "Navigation":   ["ls", "cd", "pwd", "tree"],
            "Files":        ["cat", "touch", "mkfile", "mkdir", "rm", "cp", "mv", "ln", "echo", "write", "find", "wc", "head", "tail", "stat", "chmod"],
            "Text":         ["grep", "sort", "uniq", "base64", "nano"],
            "System":       ["ps", "kill", "env", "export", "unset", "uname", "uptime", "free", "df", "ping"],
            "Users":        ["whoami", "adduser", "passwd", "users"],
            "Utilities":    ["date", "hostname", "calc", "hash", "which", "man", "clear", "banner", "history", "alias", "unalias", "ver"],
            "Notes & Cron": ["note", "cron"],
            "Persistence":  ["save", "load", "reset"],
            "Shell":        ["exit", "help"],
        }
        desc = {
            "ls": "list directory", "cd": "change directory", "pwd": "print working dir",
            "tree": "dir tree", "cat": "print file", "touch": "create empty file",
            "mkfile": "create file w/ content", "mkdir": "make directory", "rm": "remove file/dir",
            "cp": "copy file", "mv": "move/rename", "ln": "hard-link (copy)",
            "echo": "print text", "write": "write text to file",
            "find": "search files", "wc": "word/line count", "head": "first N lines",
            "tail": "last N lines", "stat": "file metadata", "chmod": "change mode",
            "grep": "search text (regex)", "sort": "sort lines", "uniq": "deduplicate lines",
            "base64": "encode/decode base64", "nano": "interactive editor",
            "ps": "process list", "kill": "kill process",
            "env": "show env vars", "export": "set env var", "unset": "unset env var",
            "uname": "system info", "uptime": "uptime info", "free": "memory usage",
            "df": "disk usage", "ping": "simulated ping",
            "date": "date/time", "whoami": "current user", "adduser": "create user",
            "passwd": "change password", "users": "list users",
            "hostname": "hostname", "calc": "calculator", "hash": "hash text",
            "which": "locate command", "man": "manual page",
            "clear": "clear screen", "banner": "show banner", "history": "command history",
            "alias": "set alias", "unalias": "remove alias", "ver": "version info",
            "note": "quick notes (persistent)", "cron": "scheduled commands",
            "save": "save state to disk", "load": "reload state from disk", "reset": "wipe all state",
            "exit": "exit PyOS", "help": "this help",
        }
        lines = [color("─" * 56, C.DIM), color("  PyOS v2.0 Command Reference", C.BOLD, C.CYAN), color("─" * 56, C.DIM)]
        for section, cmds in cols.items():
            lines.append(color(f"\n  {section}", C.YELLOW, C.BOLD))
            for cmd in cmds:
                lines.append(f"    {color(cmd.ljust(14), C.GREEN)}  {desc.get(cmd,'')}")
        lines.append(color("\n  Operators: | (pipe)  > (write)  >> (append)  $VAR (expand)", C.DIM))
        lines.append(color("  State auto-saved after every command → .pyos_state.json", C.DIM))
        lines.append(color("─" * 56, C.DIM))
        return "\n".join(lines)

    # ── Navigation ───────────────────────────
    def cmd_pwd(self, args, **_):
        return self.cwd

    def cmd_cd(self, args, **_):
        target = args[0] if args else self.env.get("HOME")
        path = self.vfs.resolve(target, self.cwd)
        if not self.vfs.exists(path):
            return color(f"cd: no such directory: {target}", C.RED)
        if not self.vfs.is_dir(path):
            return color(f"cd: not a directory: {target}", C.RED)
        self.cwd = path

    def cmd_ls(self, args, **_):
        long = "-l" in args
        all_ = "-a" in args
        path_arg = next((a for a in args if not a.startswith("-")), self.cwd)
        path = self.vfs.resolve(path_arg, self.cwd)
        if not self.vfs.exists(path):
            return color(f"ls: cannot access '{path_arg}': No such file or directory", C.RED)
        if self.vfs.is_file(path):
            items = [os.path.basename(path)]
            base = os.path.dirname(path)
        else:
            items = self.vfs.listdir(path)
            base = path
        if not all_:
            items = [i for i in items if not i.startswith(".")]
        if not long:
            # colorized columns
            parts = []
            for i in items:
                full = base.rstrip("/") + "/" + i if base != "/" else "/" + i
                if self.vfs.is_dir(full):
                    parts.append(color(i + "/", C.BLUE, C.BOLD))
                else:
                    parts.append(color(i, C.WHITE))
            return "  ".join(parts) if parts else color("(empty)", C.DIM)
        else:
            rows = []
            for i in items:
                full = base.rstrip("/") + "/" + i if base != "/" else "/" + i
                m = self.vfs.meta(full)
                size = m.get("size", "-") if self.vfs.is_file(full) else "-"
                mod  = m.get("modified", "?")
                kind = color("d", C.BLUE) if self.vfs.is_dir(full) else color("-", C.DIM)
                name = color(i + "/", C.BLUE, C.BOLD) if self.vfs.is_dir(full) else color(i, C.WHITE)
                rows.append(f"  {kind}rw-r--r--  {str(size).rjust(6)}  {mod}  {name}")
            return "\n".join(rows) if rows else color("(empty)", C.DIM)

    def cmd_tree(self, args, **_):
        path_arg = args[0] if args else self.cwd
        path = self.vfs.resolve(path_arg, self.cwd)
        if not self.vfs.is_dir(path):
            return color(f"tree: not a directory: {path_arg}", C.RED)
        lines = [color(path, C.CYAN, C.BOLD)]
        self._tree_recurse(path, "", lines)
        return "\n".join(lines)

    def _tree_recurse(self, path, prefix, lines):
        items = self.vfs.listdir(path)
        for idx, item in enumerate(items):
            full = path.rstrip("/") + "/" + item if path != "/" else "/" + item
            connector = "└── " if idx == len(items) - 1 else "├── "
            if self.vfs.is_dir(full):
                lines.append(prefix + connector + color(item + "/", C.BLUE, C.BOLD))
                ext = "    " if idx == len(items) - 1 else "│   "
                self._tree_recurse(full, prefix + ext, lines)
            else:
                lines.append(prefix + connector + color(item, C.WHITE))

    # ── File ops ─────────────────────────────
    def cmd_cat(self, args, stdin=None, **_):
        if stdin:
            return stdin
        if not args:
            return color("cat: missing operand", C.RED)
        out = []
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            try:
                out.append(self.vfs.read(path))
            except Exception as e:
                out.append(color(str(e), C.RED))
        return "".join(out)

    def cmd_touch(self, args, **_):
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            if not self.vfs.exists(path):
                try:
                    self.vfs.write(path, "")
                except Exception as e:
                    return color(str(e), C.RED)

    def cmd_mkdir(self, args, **_):
        if not args:
            return color("mkdir: missing operand", C.RED)
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            try:
                self.vfs.mkdir(path)
            except Exception as e:
                return color(str(e), C.RED)

    def cmd_rm(self, args, **_):
        if not args:
            return color("rm: missing operand", C.RED)
        recursive = "-r" in args or "-rf" in args
        targets = [a for a in args if not a.startswith("-")]
        for a in targets:
            path = self.vfs.resolve(a, self.cwd)
            try:
                self.vfs.remove(path, recursive=recursive)
            except Exception as e:
                return color(str(e), C.RED)

    def cmd_cp(self, args, **_):
        if len(args) < 2:
            return color("cp: missing operand", C.RED)
        src = self.vfs.resolve(args[0], self.cwd)
        dst = self.vfs.resolve(args[1], self.cwd)
        try:
            self.vfs.copy(src, dst)
        except Exception as e:
            return color(str(e), C.RED)

    def cmd_mv(self, args, **_):
        if len(args) < 2:
            return color("mv: missing operand", C.RED)
        src = self.vfs.resolve(args[0], self.cwd)
        dst = self.vfs.resolve(args[1], self.cwd)
        try:
            self.vfs.move(src, dst)
        except Exception as e:
            return color(str(e), C.RED)

    def cmd_echo(self, args, **_):
        text = " ".join(args)
        # basic escape sequences
        text = text.replace("\\n", "\n").replace("\\t", "\t")
        return text

    def cmd_write(self, args, **_):
        """write <file> <content...>  — write text to file"""
        if len(args) < 2:
            return color("write: usage: write <file> <content...>", C.RED)
        path = self.vfs.resolve(args[0], self.cwd)
        content = " ".join(args[1:]).replace("\\n", "\n")
        try:
            self.vfs.write(path, content + "\n")
        except Exception as e:
            return color(str(e), C.RED)

    def cmd_head(self, args, **_):
        n = 10
        targets = []
        i = 0
        while i < len(args):
            if args[i] == "-n" and i + 1 < len(args):
                n = int(args[i + 1]); i += 2
            else:
                targets.append(args[i]); i += 1
        if not targets:
            return color("head: missing file", C.RED)
        out = []
        for a in targets:
            path = self.vfs.resolve(a, self.cwd)
            try:
                lines = self.vfs.read(path).splitlines()
                out.append("\n".join(lines[:n]))
            except Exception as e:
                out.append(color(str(e), C.RED))
        return "\n".join(out)

    def cmd_tail(self, args, **_):
        n = 10
        targets = []
        i = 0
        while i < len(args):
            if args[i] == "-n" and i + 1 < len(args):
                n = int(args[i + 1]); i += 2
            else:
                targets.append(args[i]); i += 1
        if not targets:
            return color("tail: missing file", C.RED)
        out = []
        for a in targets:
            path = self.vfs.resolve(a, self.cwd)
            try:
                lines = self.vfs.read(path).splitlines()
                out.append("\n".join(lines[-n:]))
            except Exception as e:
                out.append(color(str(e), C.RED))
        return "\n".join(out)

    def cmd_wc(self, args, stdin=None, **_):
        if stdin:
            text = stdin
            label = ""
        elif args:
            path = self.vfs.resolve(args[0], self.cwd)
            try:
                text = self.vfs.read(path)
                label = args[0]
            except Exception as e:
                return color(str(e), C.RED)
        else:
            return color("wc: missing operand", C.RED)
        lines = text.count("\n")
        words = len(text.split())
        chars = len(text)
        return f"  {lines:>6}  {words:>6}  {chars:>6}  {label}"

    def cmd_find(self, args, **_):
        path_arg = args[0] if args else self.cwd
        name_pat = None
        if "-name" in args:
            i = args.index("-name")
            if i + 1 < len(args):
                name_pat = args[i + 1].replace("*", "")
        base = self.vfs.resolve(path_arg, self.cwd)
        results = []
        for k in self.vfs._tree:
            if k.startswith(base):
                if name_pat is None or name_pat in k:
                    results.append(k)
        return "\n".join(sorted(results)) if results else color("(no matches)", C.DIM)

    # ── Process ──────────────────────────────
    def cmd_ps(self, args, **_):
        rows = [color("  PID  NAME            OWNER    STATUS   STARTED", C.BOLD)]
        rows.append(color("  " + "─" * 48, C.DIM))
        for p in self.proc.list():
            row = (
                color(str(p["pid"]).rjust(5), C.YELLOW) + "  "
                + p["name"].ljust(15) + "  "
                + p["owner"].ljust(8) + " "
                + color(p["status"], C.GREEN) + "  "
                + p["started"]
            )
            rows.append("  " + row)
        return "\n".join(rows)

    def cmd_kill(self, args, **_):
        if not args:
            return color("kill: usage: kill <pid>", C.RED)
        try:
            pid = int(args[0])
        except ValueError:
            return color("kill: invalid PID", C.RED)
        if self.proc.kill(pid):
            return color(f"Process {pid} terminated.", C.GREEN)
        return color(f"kill: ({pid}) — operation not permitted or PID not found", C.RED)

    # ── Environment ──────────────────────────
    def cmd_env(self, args, **_):
        rows = []
        for k, v in sorted(self.env.all().items()):
            rows.append(color(k, C.CYAN) + "=" + v)
        return "\n".join(rows)

    def cmd_export(self, args, **_):
        if not args:
            return color("export: usage: export KEY=value", C.RED)
        for a in args:
            if "=" in a:
                k, v = a.split("=", 1)
                self.env.set(k, v)
            else:
                return color(f"export: invalid syntax: {a}", C.RED)

    def cmd_unset(self, args, **_):
        for a in args:
            self.env.unset(a)

    # ── System info ──────────────────────────
    def cmd_uname(self, args, **_):
        if "-a" in args:
            return f"PyOS pyos 1.0.0 #{random.randint(1000,9999)} SMP Python/{platform.python_version()} {platform.machine()}"
        return "PyOS"

    def cmd_uptime(self, args, **_):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        return f" {t} up forever,  1 user,  load average: 0.00, 0.00, 0.00"

    def cmd_free(self, args, **_):
        rows = [
            color("              total        used        free", C.BOLD),
            color("Mem:", C.CYAN) + "         65536       12288       53248",
            color("Swap:", C.CYAN) + "            0           0           0",
        ]
        return "\n".join(rows)

    def cmd_df(self, args, **_):
        total = sum(
            n.get("_meta", {}).get("size", 0)
            for n in self.vfs._tree.values()
            if n.get("_type") == "file"
        )
        rows = [
            color("Filesystem          Size  Used  Avail  Use%  Mounted on", C.BOLD),
            f"pyos-vfs           1024K  {total//1024}K   {(1024*1024-total)//1024}K    {total//(1024*10)}%   /",
        ]
        return "\n".join(rows)

    # ── Utilities ────────────────────────────
    def cmd_date(self, args, **_):
        return datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y")

    def cmd_whoami(self, args, **_):
        return self.env.get("USER")

    def cmd_hostname(self, args, **_):
        return "pyos"

    def cmd_calc(self, args, **_):
        if not args:
            return color("calc: usage: calc <expression>  e.g. calc 2+2", C.RED)
        expr = " ".join(args)
        try:
            # safe-ish eval
            allowed = set("0123456789+-*/(). %")
            if not all(c in allowed for c in expr):
                return color("calc: unsafe characters in expression", C.RED)
            result = eval(expr)  # noqa
            return f"{expr} = {result}"
        except Exception as e:
            return color(f"calc: error: {e}", C.RED)

    def cmd_hash(self, args, **_):
        if not args:
            return color("hash: usage: hash <text>", C.RED)
        text = " ".join(args).encode()
        md5    = hashlib.md5(text).hexdigest()
        sha256 = hashlib.sha256(text).hexdigest()
        return f"  MD5:    {color(md5, C.CYAN)}\n  SHA256: {color(sha256, C.CYAN)}"

    def cmd_clear(self, args, **_):
        print("\033[2J\033[H", end="")

    def cmd_banner(self, args, **_):
        print(color(self.BANNER, C.CYAN, C.BOLD))

    def cmd_history(self, args, **_):
        cmds = self.hist.all()
        if not cmds:
            return color("(no history)", C.DIM)
        return "\n".join(f"  {color(str(i+1).rjust(4), C.DIM)}  {cmd}" for i, cmd in enumerate(cmds))

    def cmd_alias(self, args, **_):
        if not args:
            if not self._aliases:
                return color("(no aliases)", C.DIM)
            return "\n".join(f"  {color(k, C.YELLOW)}={v}" for k, v in self._aliases.items())
        for a in args:
            if "=" in a:
                k, v = a.split("=", 1)
                self._aliases[k] = v
            else:
                return color(f"alias: invalid syntax: {a}", C.RED)

    def cmd_unalias(self, args, **_):
        for a in args:
            self._aliases.pop(a, None)

    # ── grep ─────────────────────────────────
    def cmd_grep(self, args, stdin=None, **_):
        """grep [-i] [-n] [-v] <pattern> [file...]"""
        if not args:
            return color("grep: usage: grep [-inv] <pattern> [file...]", C.RED)
        ignore_case = "-i" in args
        show_nums   = "-n" in args
        invert      = "-v" in args
        clean_args  = [a for a in args if not a.startswith("-")]
        if not clean_args:
            return color("grep: missing pattern", C.RED)
        pattern = clean_args[0]
        flags = re.IGNORECASE if ignore_case else 0
        try:
            rx = re.compile(pattern, flags)
        except re.error as e:
            return color(f"grep: invalid regex: {e}", C.RED)

        def search_text(text, label=""):
            out = []
            for i, line in enumerate(text.splitlines(), 1):
                match = bool(rx.search(line))
                if invert:
                    match = not match
                if match:
                    highlighted = rx.sub(lambda m: color(m.group(), C.RED, C.BOLD), line) if not invert else line
                    prefix = color(f"{label}{i}:", C.CYAN) if show_nums else (color(f"{label}", C.MAGENTA) if label else "")
                    out.append(prefix + highlighted)
            return out

        if stdin and len(clean_args) == 1:
            results = search_text(stdin)
            return "\n".join(results) if results else color("(no matches)", C.DIM)

        files = clean_args[1:]
        if not files:
            return color("grep: no files and no piped input", C.RED)
        all_out = []
        for f in files:
            path = self.vfs.resolve(f, self.cwd)
            try:
                text = self.vfs.read(path)
                label = f"{f}:" if len(files) > 1 else ""
                all_out.extend(search_text(text, label))
            except Exception as e:
                all_out.append(color(str(e), C.RED))
        return "\n".join(all_out) if all_out else color("(no matches)", C.DIM)

    # ── sort ─────────────────────────────────
    def cmd_sort(self, args, stdin=None, **_):
        """sort [-r] [-u] [file]"""
        reverse = "-r" in args
        unique  = "-u" in args
        clean   = [a for a in args if not a.startswith("-")]
        if stdin:
            text = stdin
        elif clean:
            path = self.vfs.resolve(clean[0], self.cwd)
            try:
                text = self.vfs.read(path)
            except Exception as e:
                return color(str(e), C.RED)
        else:
            return color("sort: missing input", C.RED)
        lines = text.splitlines()
        lines.sort(reverse=reverse)
        if unique:
            seen, deduped = set(), []
            for l in lines:
                if l not in seen:
                    seen.add(l)
                    deduped.append(l)
            lines = deduped
        return "\n".join(lines)

    # ── uniq ─────────────────────────────────
    def cmd_uniq(self, args, stdin=None, **_):
        """uniq [-c] [file] — filter adjacent duplicate lines"""
        count = "-c" in args
        clean = [a for a in args if not a.startswith("-")]
        if stdin:
            text = stdin
        elif clean:
            path = self.vfs.resolve(clean[0], self.cwd)
            try:
                text = self.vfs.read(path)
            except Exception as e:
                return color(str(e), C.RED)
        else:
            return color("uniq: missing input", C.RED)
        lines = text.splitlines()
        out, prev, cnt = [], None, 0
        for line in lines:
            if line == prev:
                cnt += 1
            else:
                if prev is not None:
                    out.append((color(f"{cnt:>4} ", C.CYAN) if count else "") + prev)
                prev, cnt = line, 1
        if prev is not None:
            out.append((color(f"{cnt:>4} ", C.CYAN) if count else "") + prev)
        return "\n".join(out)

    # ── base64 ───────────────────────────────
    def cmd_base64(self, args, stdin=None, **_):
        """base64 [-d] <text|file>"""
        decode = "-d" in args
        clean  = [a for a in args if not a.startswith("-")]
        if stdin:
            text = stdin.strip()
        elif clean:
            # check if it's a file path first
            path = self.vfs.resolve(clean[0], self.cwd)
            if self.vfs.is_file(path):
                text = self.vfs.read(path).strip()
            else:
                text = " ".join(clean)
        else:
            return color("base64: usage: base64 [-d] <text|file>", C.RED)
        try:
            if decode:
                result = _base64.b64decode(text.encode()).decode()
            else:
                result = _base64.b64encode(text.encode()).decode()
            return result
        except Exception as e:
            return color(f"base64: error: {e}", C.RED)

    # ── stat ─────────────────────────────────
    def cmd_stat(self, args, **_):
        """stat <file|dir>"""
        if not args:
            return color("stat: missing operand", C.RED)
        out = []
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            if not self.vfs.exists(path):
                out.append(color(f"stat: {a}: No such file or directory", C.RED))
                continue
            m = self.vfs.meta(path)
            kind = "directory" if self.vfs.is_dir(path) else "regular file"
            size = m.get("size", 0) if self.vfs.is_file(path) else "-"
            out.append(
                f"  {color('File:', C.BOLD)} {path}\n"
                f"  {color('Type:', C.BOLD)} {kind}\n"
                f"  {color('Size:', C.BOLD)} {size} bytes\n"
                f"  {color('Created:', C.BOLD)}  {m.get('created','?')}\n"
                f"  {color('Modified:', C.BOLD)} {m.get('modified','?')}"
            )
        return "\n".join(out)

    # ── chmod (cosmetic) ─────────────────────
    def cmd_chmod(self, args, **_):
        """chmod <mode> <file> — updates metadata only"""
        if len(args) < 2:
            return color("chmod: usage: chmod <mode> <file>", C.RED)
        mode, target = args[0], args[1]
        path = self.vfs.resolve(target, self.cwd)
        if not self.vfs.exists(path):
            return color(f"chmod: {target}: No such file or directory", C.RED)
        self.vfs._tree[path]["_meta"]["mode"] = mode
        return color(f"mode of '{target}' changed to {mode}", C.GREEN)

    # ── nano (interactive editor) ─────────────
    def cmd_nano(self, args, **_):
        """nano <file> — simple interactive line editor"""
        if not args:
            return color("nano: usage: nano <file>", C.RED)
        path = self.vfs.resolve(args[0], self.cwd)
        existing = ""
        if self.vfs.is_file(path):
            existing = self.vfs.read(path)

        print(color(f"\n  ┌─ nano: {path} ─────────────────────────────", C.CYAN, C.BOLD))
        print(color("  │  Enter lines. Type ':w' to save, ':q' to quit, ':wq' to save+quit.", C.DIM))
        if existing:
            print(color("  │  Current content:", C.DIM))
            for i, l in enumerate(existing.splitlines(), 1):
                print(color(f"  │  {i:>3}  ", C.DIM) + l)
        print(color("  └────────────────────────────────────────────", C.CYAN, C.BOLD))

        lines = list(existing.splitlines())
        new_lines = []
        saved = False
        while True:
            try:
                entry = input(color("  > ", C.GREEN))
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if entry == ":wq":
                lines = lines + new_lines
                try:
                    self.vfs.write(path, "\n".join(lines) + "\n")
                    saved = True
                except Exception as e:
                    print(color(f"  Error: {e}", C.RED))
                break
            elif entry == ":w":
                lines = lines + new_lines
                new_lines = []
                try:
                    self.vfs.write(path, "\n".join(lines) + "\n")
                    saved = True
                    print(color(f"  Saved {len(lines)} lines.", C.GREEN))
                except Exception as e:
                    print(color(f"  Error: {e}", C.RED))
            elif entry == ":q":
                break
            elif entry.startswith(":dd"):
                # delete last line
                if lines:
                    removed = lines.pop()
                    print(color(f"  Deleted: {removed}", C.DIM))
                elif new_lines:
                    removed = new_lines.pop()
                    print(color(f"  Deleted: {removed}", C.DIM))
            else:
                new_lines.append(entry)
        msg = color(f"  Saved → {path}", C.GREEN) if saved else color("  nano: quit without saving.", C.DIM)
        print(msg)

    # ── ver ──────────────────────────────────
    def cmd_ver(self, args, **_):
        return (
            f"  {color('PyOS', C.CYAN, C.BOLD)} v2.0\n"
            f"  Python {platform.python_version()} on {platform.system()} {platform.machine()}\n"
            f"  State file: {color(STATE_FILE, C.DIM)}"
        )

    # ── save / load ──────────────────────────
    def cmd_save(self, args, **_):
        """Manually save state to disk."""
        result = self._save_state()
        if result is True:
            return color(f"  State saved to {STATE_FILE}", C.GREEN)
        return color(f"  Save failed: {result}", C.RED)

    def cmd_load(self, args, **_):
        """Reload state from disk."""
        self._load_state()
        return color(f"  State reloaded from {STATE_FILE}", C.GREEN)

    # ── adduser / passwd ─────────────────────
    def cmd_adduser(self, args, **_):
        """adduser <username>"""
        if not args:
            return color("adduser: usage: adduser <username>", C.RED)
        name = args[0]
        if name in self._users:
            return color(f"adduser: user '{name}' already exists", C.RED)
        home = f"/home/{name}"
        self._users[name] = {"password": hashlib.sha256(b"").hexdigest(), "home": home}
        try:
            self.vfs.mkdir(f"/home/{name}")
        except Exception:
            pass
        return color(f"User '{name}' created. Home: {home}", C.GREEN)

    def cmd_passwd(self, args, **_):
        """passwd [username] — change password"""
        user = args[0] if args else self.env.get("USER")
        if user not in self._users:
            return color(f"passwd: user '{user}' not found", C.RED)
        try:
            pw = input(color(f"  New password for {user}: ", C.YELLOW))
            pw2 = input(color("  Confirm password: ", C.YELLOW))
        except (EOFError, KeyboardInterrupt):
            print()
            return color("  passwd: cancelled.", C.DIM)
        if pw != pw2:
            return color("  passwd: passwords do not match.", C.RED)
        self._users[user]["password"] = hashlib.sha256(pw.encode()).hexdigest()
        return color(f"  Password updated for '{user}'.", C.GREEN)

    def cmd_users(self, args, **_):
        """List all users."""
        rows = [color("  USER            HOME", C.BOLD)]
        rows.append(color("  " + "─" * 30, C.DIM))
        for u, info in self._users.items():
            rows.append(f"  {color(u.ljust(15), C.CYAN)}  {info.get('home','?')}")
        return "\n".join(rows)

    # ── note ─────────────────────────────────
    def cmd_note(self, args, **_):
        """note [add <text>] [list] [del <id>] [clear]"""
        sub = args[0] if args else "list"
        if sub == "add":
            if len(args) < 2:
                return color("note: usage: note add <text>", C.RED)
            text = " ".join(args[1:])
            ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            self._notes.append({"id": len(self._notes) + 1, "ts": ts, "text": text})
            return color(f"  Note #{len(self._notes)} added.", C.GREEN)
        elif sub == "list":
            if not self._notes:
                return color("  (no notes)", C.DIM)
            rows = [color("  ID   DATE-TIME        NOTE", C.BOLD)]
            for n in self._notes:
                rows.append(f"  {color(str(n['id']).rjust(2), C.YELLOW)}   {color(n['ts'], C.DIM)}  {n['text']}")
            return "\n".join(rows)
        elif sub == "del":
            if len(args) < 2:
                return color("note: usage: note del <id>", C.RED)
            try:
                nid = int(args[1])
            except ValueError:
                return color("note: invalid id", C.RED)
            before = len(self._notes)
            self._notes = [n for n in self._notes if n["id"] != nid]
            if len(self._notes) < before:
                return color(f"  Note #{nid} deleted.", C.GREEN)
            return color(f"  Note #{nid} not found.", C.RED)
        elif sub == "clear":
            self._notes = []
            return color("  All notes cleared.", C.GREEN)
        return color(f"note: unknown subcommand: {sub}", C.RED)

    # ── cron ─────────────────────────────────
    def cmd_cron(self, args, **_):
        """cron [add <interval_sec> <cmd>] [list] [del <id>] — simulated scheduler (runs on next prompt)"""
        sub = args[0] if args else "list"
        if sub == "add":
            if len(args) < 3:
                return color("cron: usage: cron add <interval_seconds> <command>", C.RED)
            try:
                interval = int(args[1])
            except ValueError:
                return color("cron: interval must be an integer", C.RED)
            cmd = " ".join(args[2:])
            entry = {"id": len(self._cron) + 1, "interval": interval, "cmd": cmd, "last": 0}
            self._cron.append(entry)
            return color(f"  Cron job #{entry['id']} added: every {interval}s → {cmd}", C.GREEN)
        elif sub == "list":
            if not self._cron:
                return color("  (no cron jobs)", C.DIM)
            rows = [color("  ID   INTERVAL  COMMAND", C.BOLD)]
            for j in self._cron:
                rows.append(f"  {color(str(j['id']).rjust(2), C.YELLOW)}   {str(j['interval']).rjust(6)}s  {j['cmd']}")
            return "\n".join(rows)
        elif sub == "del":
            if len(args) < 2:
                return color("cron: usage: cron del <id>", C.RED)
            try:
                jid = int(args[1])
            except ValueError:
                return color("cron: invalid id", C.RED)
            before = len(self._cron)
            self._cron = [j for j in self._cron if j["id"] != jid]
            return color(f"  Cron job #{jid} removed.", C.GREEN) if len(self._cron) < before else color(f"  Job #{jid} not found.", C.RED)
        return color(f"cron: unknown subcommand: {sub}", C.RED)

    def _run_cron(self):
        """Called before every prompt to fire due cron jobs."""
        now = time.time()
        for job in self._cron:
            if now - job.get("last", 0) >= job["interval"]:
                job["last"] = now
                print(color(f"\n  [cron] running: {job['cmd']}", C.DIM))
                self.run_line(job["cmd"])

    # ── ping (simulated) ─────────────────────
    def cmd_ping(self, args, **_):
        """ping <host> [-c <count>]"""
        if not args:
            return color("ping: usage: ping <host> [-c <count>]", C.RED)
        host = next((a for a in args if not a.startswith("-")), None)
        count = 4
        if "-c" in args:
            i = args.index("-c")
            if i + 1 < len(args):
                try:
                    count = int(args[i + 1])
                except ValueError:
                    pass
        if not host:
            return color("ping: missing host", C.RED)
        rows = [color(f"  PING {host}: 56 data bytes", C.BOLD)]
        for i in range(1, count + 1):
            ms = round(random.uniform(0.5, 80.0), 3)
            rows.append(f"  64 bytes from {host}: icmp_seq={i} ttl=64 time={ms} ms")
        rows.append(color(f"\n  --- {host} ping statistics ---", C.DIM))
        rows.append(f"  {count} packets transmitted, {count} received, 0% packet loss")
        return "\n".join(rows)

    # ── man ──────────────────────────────────
    def cmd_man(self, args, **_):
        """man <command> — show manual page"""
        manpages = {
            "ls":      "ls [-l] [-a] [path]\n    List directory contents. -l for long format, -a to show hidden files.",
            "cd":      "cd [path]\n    Change directory. No argument goes to HOME.",
            "cat":     "cat <file...>\n    Print file contents to stdout.",
            "grep":    "grep [-i] [-n] [-v] <pattern> [file...]\n    Search text. -i ignore case, -n show line numbers, -v invert match.",
            "nano":    "nano <file>\n    Interactive line editor. :w save, :q quit, :wq save+quit, :dd delete last line.",
            "note":    "note [add <text>] [list] [del <id>] [clear]\n    Persistent quick notes.",
            "cron":    "cron [add <secs> <cmd>] [list] [del <id>]\n    Simulated scheduler that runs commands every N seconds.",
            "sort":    "sort [-r] [-u] [file]\n    Sort lines. -r reverse, -u unique.",
            "uniq":    "uniq [-c] [file]\n    Filter adjacent duplicates. -c prefix count.",
            "base64":  "base64 [-d] <text|file>\n    Encode/decode base64. -d to decode.",
            "stat":    "stat <file|dir>\n    Show file metadata (size, timestamps, mode).",
            "chmod":   "chmod <mode> <file>\n    Change file mode (cosmetic).",
            "ping":    "ping <host> [-c <count>]\n    Simulated network ping.",
            "save":    "save\n    Manually save PyOS state to disk.",
            "load":    "load\n    Reload PyOS state from disk.",
            "adduser": "adduser <username>\n    Create a new user account.",
            "passwd":  "passwd [username]\n    Change a user's password.",
            "users":   "users\n    List all users.",
            "ver":     "ver\n    Show PyOS version and system info.",
            "hash":    "hash <text>\n    Print MD5 and SHA256 of text.",
            "calc":    "calc <expression>\n    Safe arithmetic calculator.",
            "find":    "find [path] [-name <pattern>]\n    Search for files in VFS.",
            "wc":      "wc [file]\n    Count lines, words, characters.",
            "tree":    "tree [path]\n    Recursive directory tree.",
            "ps":      "ps\n    List running processes.",
            "kill":    "kill <pid>\n    Terminate a user process.",
            "env":     "env\n    Show all environment variables.",
            "export":  "export KEY=value\n    Set an environment variable.",
            "history": "history\n    Show command history.",
            "alias":   "alias [name=value]\n    Create or list command aliases.",
        }
        if not args:
            return color("man: usage: man <command>", C.RED)
        cmd = args[0]
        if cmd in manpages:
            return (
                color(f"\n  MAN PAGE: {cmd}", C.BOLD, C.CYAN) + "\n"
                + color("  " + "─" * 40, C.DIM) + "\n"
                + "\n".join("  " + l for l in manpages[cmd].splitlines()) + "\n"
                + color("  " + "─" * 40, C.DIM)
            )
        return color(f"man: no manual entry for '{cmd}'", C.RED)

    # ── touch with content ───────────────────
    def cmd_mkfile(self, args, **_):
        """mkfile <file> [content...] — create file with optional content"""
        if not args:
            return color("mkfile: usage: mkfile <file> [content...]", C.RED)
        path = self.vfs.resolve(args[0], self.cwd)
        content = " ".join(args[1:]) if len(args) > 1 else ""
        try:
            self.vfs.write(path, content + ("\n" if content else ""))
            return color(f"Created: {path}", C.GREEN)
        except Exception as e:
            return color(str(e), C.RED)

    # ── ln (symlink-style alias) ─────────────
    def cmd_ln(self, args, **_):
        """ln <src> <dst> — create a hard copy (VFS has no real symlinks)"""
        if len(args) < 2:
            return color("ln: usage: ln <src> <dst>", C.RED)
        src = self.vfs.resolve(args[0], self.cwd)
        dst = self.vfs.resolve(args[1], self.cwd)
        try:
            self.vfs.copy(src, dst)
            return color(f"Linked: {src} → {dst}", C.GREEN)
        except Exception as e:
            return color(str(e), C.RED)

    # ── which ────────────────────────────────
    def cmd_which(self, args, **_):
        """which <command> — show where a command lives"""
        if not args:
            return color("which: usage: which <command>", C.RED)
        out = []
        for cmd in args:
            if hasattr(self, f"cmd_{cmd}"):
                out.append(f"  {color(cmd, C.GREEN)}: built-in pysh command")
            elif cmd in self._aliases:
                out.append(f"  {color(cmd, C.YELLOW)}: alias → {self._aliases[cmd]}")
            else:
                out.append(color(f"  {cmd}: not found", C.RED))
        return "\n".join(out)

    # ── reset-state ──────────────────────────
    def cmd_reset(self, args, **_):
        """reset — wipe persistent state and restart fresh"""
        try:
            confirm = input(color("  This will erase all saved state. Type 'yes' to confirm: ", C.RED))
        except (EOFError, KeyboardInterrupt):
            print()
            return color("  Reset cancelled.", C.DIM)
        if confirm.strip().lower() == "yes":
            try:
                os.remove(STATE_FILE)
            except FileNotFoundError:
                pass
            return color("  State wiped. Restart PyOS to begin fresh.", C.YELLOW)
        return color("  Reset cancelled.", C.DIM)

    def cmd_exit(self, args, **_):
        self._save_state()
        self.running = False
        print(color("\n  Goodbye from PyOS. State saved. Shutting down...\n", C.YELLOW, C.BOLD))

    # ─────────────────────────────────────────
    #  MAIN LOOP
    # ─────────────────────────────────────────
    def run(self):
        os.system("clear" if os.name != "nt" else "cls")
        print(color(self.BANNER, C.CYAN, C.BOLD))
        print(color("  Type 'help' for commands. Type 'exit' to quit.\n", C.DIM))

        # show MOTD
        try:
            print(color("  " + self.vfs.read("/etc/motd").strip(), C.YELLOW) + "\n")
        except Exception:
            pass

        while self.running:
            try:
                self._run_cron()
                line = input(self._prompt())
            except (EOFError, KeyboardInterrupt):
                print()
                continue
            self.run_line(line)

        sys.exit(0)


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    Shell().run()