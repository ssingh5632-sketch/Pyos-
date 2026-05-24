#!/usr/bin/env python3
"""
PyOS GUI — A desktop-style OS simulator built with tkinter.
Run: python3 pyos_gui.py
Requires: Python 3.8+ with tkinter (standard library)
"""

import os, sys, re, json, time, random, hashlib, platform
import datetime, base64 as _base64, threading
import tkinter as tk
from tkinter import ttk, font as tkfont, messagebox, simpledialog

# ─────────────────────────────────────────────────────────────────────────────
#  PERSISTENT STATE
# ─────────────────────────────────────────────────────────────────────────────
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".pyos_gui_state.json")

# ─────────────────────────────────────────────────────────────────────────────
#  COLOUR PALETTE  (dark theme)
# ─────────────────────────────────────────────────────────────────────────────
PAL = dict(
    bg       = "#0d1117",   # window background
    panel    = "#161b22",   # sidebar / panels
    border   = "#30363d",   # dividers
    accent   = "#58a6ff",   # blue highlight
    green    = "#3fb950",
    yellow   = "#d29922",
    red      = "#f85149",
    cyan     = "#39c5cf",
    magenta  = "#bc8cff",
    dim      = "#484f58",
    fg       = "#c9d1d9",   # normal text
    fg_dim   = "#8b949e",
    sel      = "#1f6feb",   # selection bg
    header   = "#21262d",   # title bars
    input_bg = "#0d1117",
    btn      = "#21262d",
    btn_h    = "#30363d",
    term_bg  = "#0d1117",
    term_fg  = "#c9d1d9",
)

# ─────────────────────────────────────────────────────────────────────────────
#  VIRTUAL FILE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────
class VFS:
    def __init__(self):
        now = self._ts()
        self._tree = {
            "/":                  {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/home":              {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/home/user":         {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/home/user/Documents":{"_type":"dir", "_meta":{"created":now,"modified":now}},
            "/home/user/Downloads":{"_type":"dir", "_meta":{"created":now,"modified":now}},
            "/etc":               {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/bin":               {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/tmp":               {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/var":               {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/var/log":           {"_type":"dir",  "_meta":{"created":now,"modified":now}},
            "/home/user/readme.txt": {
                "_type":"file","_data":"Welcome to PyOS GUI!\nType 'help' in the terminal for commands.\n",
                "_meta":{"created":now,"modified":now,"size":60}},
            "/etc/motd": {
                "_type":"file","_data":"PyOS GUI 2.0 — Python Desktop OS Simulator\n",
                "_meta":{"created":now,"modified":now,"size":43}},
            "/var/log/syslog": {
                "_type":"file","_data":f"[{now}] PyOS GUI kernel started.\n",
                "_meta":{"created":now,"modified":now,"size":40}},
        }

    @staticmethod
    def _ts():
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _normalize(self, path, cwd="/"):
        if not path.startswith("/"):
            path = cwd.rstrip("/") + "/" + path
        parts = []
        for p in path.split("/"):
            if p in ("", "."):   continue
            elif p == "..":
                if parts: parts.pop()
            else:
                parts.append(p)
        return "/" + "/".join(parts)

    def exists(self, p):    return p in self._tree
    def is_dir(self, p):    return self._tree.get(p,{}).get("_type") == "dir"
    def is_file(self, p):   return self._tree.get(p,{}).get("_type") == "file"
    def resolve(self, p, cwd): return self._normalize(p, cwd)
    def meta(self, p):      return self._tree.get(p,{}).get("_meta",{})

    def listdir(self, path):
        path = path.rstrip("/") if path != "/" else "/"
        prefix = path if path == "/" else path + "/"
        children = []
        for k in self._tree:
            if k == path: continue
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
            if append: data = self._tree[path]["_data"] + data
            self._tree[path]["_data"] = data
            self._tree[path]["_meta"]["modified"] = now
            self._tree[path]["_meta"]["size"] = len(data)
        else:
            parent = "/".join(path.split("/")[:-1]) or "/"
            if not self.is_dir(parent):
                raise FileNotFoundError(f"No such directory: {parent}")
            self._tree[path] = {"_type":"file","_data":data,
                                "_meta":{"created":now,"modified":now,"size":len(data)}}

    def mkdir(self, path):
        if self.exists(path): raise FileExistsError(f"Already exists: {path}")
        parent = "/".join(path.split("/")[:-1]) or "/"
        if not self.is_dir(parent): raise FileNotFoundError(f"No such directory: {parent}")
        now = self._ts()
        self._tree[path] = {"_type":"dir","_meta":{"created":now,"modified":now}}

    def remove(self, path, recursive=False):
        if not self.exists(path): raise FileNotFoundError(f"No such file or directory: {path}")
        if self.is_dir(path):
            children = [k for k in self._tree if k != path and k.startswith(path+"/")]
            if children and not recursive:
                raise PermissionError(f"Directory not empty (use -r): {path}")
            for c in children: del self._tree[c]
        del self._tree[path]

    def copy(self, src, dst):
        if not self.is_file(src): raise FileNotFoundError(f"No such file: {src}")
        self.write(dst, self.read(src))

    def move(self, src, dst):
        self.copy(src, dst); self.remove(src)

    def to_dict(self):   return self._tree
    def from_dict(self, d): self._tree = d

    def log(self, msg):
        try: self.write("/var/log/syslog", f"[{self._ts()}] {msg}\n", append=True)
        except: pass

# ─────────────────────────────────────────────────────────────────────────────
#  PROCESS TABLE
# ─────────────────────────────────────────────────────────────────────────────
class ProcessTable:
    def __init__(self):
        self._procs = {}; self._next = 1
        for name, owner in [("kernel","system"),("init","system"),("gui-shell","user")]:
            self.add(name, owner)

    def add(self, name, owner="user"):
        pid = self._next; self._next += 1
        self._procs[pid] = {"pid":pid,"name":name,"owner":owner,
            "started":datetime.datetime.now().strftime("%H:%M:%S"),"status":"running"}
        return pid

    def kill(self, pid):
        if pid not in self._procs: return False
        if self._procs[pid]["owner"] == "system": return False
        del self._procs[pid]; return True

    def list(self): return list(self._procs.values())

# ─────────────────────────────────────────────────────────────────────────────
#  ENV + HISTORY
# ─────────────────────────────────────────────────────────────────────────────
class Env:
    def __init__(self):
        self._v = {"SHELL":"/bin/pysh","USER":"user","HOME":"/home/user",
                   "PATH":"/bin:/usr/bin","OS":"PyOS","VER":"2.0","TERM":"pyterm"}
    def get(self, k, d=""): return self._v.get(k, d)
    def set(self, k, v):    self._v[k] = v
    def unset(self, k):     self._v.pop(k, None)
    def all(self):          return dict(self._v)
    def to_dict(self):      return dict(self._v)
    def from_dict(self, d): self._v.update(d)

class History:
    def __init__(self):   self._c = []
    def add(self, cmd):
        if cmd.strip(): self._c.append(cmd)
    def all(self):        return self._c
    def to_list(self):    return list(self._c)
    def from_list(self, d): self._c = list(d)

# ─────────────────────────────────────────────────────────────────────────────
#  SHELL ENGINE  (pure logic, no I/O)
# ─────────────────────────────────────────────────────────────────────────────
class Shell:
    def __init__(self, on_output=None, on_refresh=None):
        self.vfs  = VFS()
        self.env  = Env()
        self.proc = ProcessTable()
        self.hist = History()
        self.cwd  = "/home/user"
        self._aliases = {}
        self._users   = {"user":{"password":hashlib.sha256(b"").hexdigest(),"home":"/home/user"}}
        self._cron    = []
        self._notes   = []
        self.on_output  = on_output  or (lambda t, tag="": None)
        self.on_refresh = on_refresh or (lambda: None)
        self._load_state()

    # ── state ────────────────────────────────
    def _save_state(self):
        state = {"vfs":self.vfs.to_dict(),"env":self.env.to_dict(),
                 "aliases":self._aliases,"history":self.hist.to_list(),
                 "cwd":self.cwd,"users":self._users,"cron":self._cron,"notes":self._notes}
        try:
            with open(STATE_FILE,"w") as f: json.dump(state,f,indent=2)
        except: pass

    def _load_state(self):
        if not os.path.exists(STATE_FILE): return
        try:
            with open(STATE_FILE) as f: s = json.load(f)
            if "vfs"     in s: self.vfs.from_dict(s["vfs"])
            if "env"     in s: self.env.from_dict(s["env"])
            if "aliases" in s: self._aliases = s["aliases"]
            if "history" in s: self.hist.from_list(s["history"])
            if "cwd"     in s: self.cwd = s["cwd"]
            if "users"   in s: self._users = s["users"]
            if "cron"    in s: self._cron = s["cron"]
            if "notes"   in s: self._notes = s["notes"]
        except: pass

    # ── tokenizer / parser ───────────────────
    @staticmethod
    def _tokenize(line):
        tokens, buf, in_q, qc = [], [], False, None
        for ch in line:
            if in_q:
                if ch == qc: in_q = False
                else: buf.append(ch)
            elif ch in ('"',"'"):
                in_q, qc = True, ch
            elif ch == " ":
                if buf: tokens.append("".join(buf)); buf=[]
            else: buf.append(ch)
        if buf: tokens.append("".join(buf))
        return tokens

    def _expand(self, t):
        return self.env.get(t[1:]) if t.startswith("$") else t

    def prompt_str(self):
        path = self.cwd.replace(self.env.get("HOME"), "~")
        return f"{self.env.get('USER')}@pyos:{path}$ "

    # ── run ──────────────────────────────────
    def run_line(self, line):
        line = line.strip()
        if not line or line.startswith("#"): return
        self.hist.add(line)

        # alias expand
        parts = line.split(None,1)
        if parts[0] in self._aliases:
            line = self._aliases[parts[0]] + (" "+parts[1] if len(parts)>1 else "")

        # pipeline
        stages = [s.strip() for s in line.split("|")]
        output = None
        for stage in stages:
            output = self._run_cmd(stage, piped_input=output)

        if output is not None:
            self.on_output(output, "output")

        self._save_state()
        self.on_refresh()

    def _run_cmd(self, line, piped_input=None):
        tokens = self._tokenize(line)
        if not tokens: return None
        tokens = [self._expand(t) for t in tokens]

        # redirects
        redirect_file, redirect_append = None, False
        clean = []; i = 0
        while i < len(tokens):
            if tokens[i] in (">",">>") and i+1 < len(tokens):
                redirect_append = tokens[i] == ">>"
                redirect_file   = self.vfs.resolve(tokens[i+1], self.cwd)
                i += 2
            else:
                clean.append(tokens[i]); i += 1
        tokens = clean
        if not tokens: return None

        cmd, args = tokens[0], tokens[1:]
        method = getattr(self, f"cmd_{cmd}", None)

        if method:
            result = method(args, stdin=piped_input)
        else:
            result = f"pysh: command not found: {cmd}  (type 'help')"

        if redirect_file and result is not None:
            try: self.vfs.write(redirect_file, (result or ""), append=redirect_append)
            except Exception as e: return str(e)
            return None
        return result

    # ─────────────────────────────────────────
    #  COMMANDS  (return str or None)
    # ─────────────────────────────────────────
    def cmd_help(self, args, **_):
        cols = {
            "Navigation":    ["ls","cd","pwd","tree"],
            "Files":         ["cat","touch","mkfile","mkdir","rm","cp","mv","ln","echo","write","find","wc","head","tail","stat","chmod"],
            "Text":          ["grep","sort","uniq","base64","nano"],
            "System":        ["ps","kill","env","export","unset","uname","uptime","free","df","ping"],
            "Users":         ["whoami","adduser","passwd","users"],
            "Utilities":     ["date","hostname","calc","hash","which","man","clear","banner","history","alias","unalias","ver"],
            "Notes & Cron":  ["note","cron"],
            "Persistence":   ["save","load","reset"],
        }
        desc = {
            "ls":"list directory","cd":"change directory","pwd":"working dir","tree":"dir tree",
            "cat":"print file","touch":"create empty file","mkfile":"create file w/ content",
            "mkdir":"make directory","rm":"remove","cp":"copy","mv":"move/rename","ln":"hard-link",
            "echo":"print text","write":"write to file","find":"search files","wc":"word count",
            "head":"first N lines","tail":"last N lines","stat":"file metadata","chmod":"change mode",
            "grep":"regex search","sort":"sort lines","uniq":"deduplicate","base64":"encode/decode",
            "nano":"edit file","ps":"process list","kill":"kill process","env":"env vars",
            "export":"set env var","unset":"unset var","uname":"system info","uptime":"uptime",
            "free":"memory","df":"disk usage","ping":"simulated ping","whoami":"current user",
            "adduser":"create user","passwd":"change password","users":"list users",
            "date":"date/time","hostname":"hostname","calc":"calculator","hash":"hash text",
            "which":"locate command","man":"manual","clear":"clear terminal","banner":"show banner",
            "history":"command history","alias":"set alias","unalias":"remove alias","ver":"version",
            "note":"quick notes","cron":"scheduled commands","save":"save state",
            "load":"reload state","reset":"wipe state",
        }
        lines = ["─"*54, "  PyOS GUI v2.0 — Command Reference", "─"*54]
        for sec, cmds in cols.items():
            lines.append(f"\n  [{sec}]")
            for c in cmds:
                lines.append(f"    {c:<14}  {desc.get(c,'')}")
        lines.append("\n  Operators: | (pipe)  > (write)  >> (append)  $VAR")
        lines.append("─"*54)
        return "\n".join(lines)

    # navigation
    def cmd_pwd(self, args, **_):   return self.cwd
    def cmd_cd(self, args, **_):
        target = args[0] if args else self.env.get("HOME")
        path = self.vfs.resolve(target, self.cwd)
        if not self.vfs.exists(path):   return f"cd: no such directory: {target}"
        if not self.vfs.is_dir(path):   return f"cd: not a directory: {target}"
        self.cwd = path

    def cmd_ls(self, args, **_):
        long = "-l" in args; all_ = "-a" in args
        path_arg = next((a for a in args if not a.startswith("-")), self.cwd)
        path = self.vfs.resolve(path_arg, self.cwd)
        if not self.vfs.exists(path): return f"ls: no such file or directory: {path_arg}"
        items = self.vfs.listdir(path) if self.vfs.is_dir(path) else [os.path.basename(path)]
        base  = path if self.vfs.is_dir(path) else os.path.dirname(path)
        if not all_: items = [i for i in items if not i.startswith(".")]
        if not long: return "  ".join(
            (i+"/" if self.vfs.is_dir(base.rstrip("/")+"/"+i) else i) for i in items
        ) or "(empty)"
        rows = []
        for i in items:
            full = base.rstrip("/")+"/"+i if base != "/" else "/"+i
            m    = self.vfs.meta(full)
            size = m.get("size","-") if self.vfs.is_file(full) else "-"
            kind = "d" if self.vfs.is_dir(full) else "-"
            rows.append(f"  {kind}rw-r--r--  {str(size):>6}  {m.get('modified','?')}  {i+('/' if self.vfs.is_dir(full) else '')}")
        return "\n".join(rows) or "(empty)"

    def cmd_tree(self, args, **_):
        path_arg = args[0] if args else self.cwd
        path = self.vfs.resolve(path_arg, self.cwd)
        if not self.vfs.is_dir(path): return f"tree: not a directory: {path_arg}"
        lines = [path]; self._tree_r(path, "", lines)
        return "\n".join(lines)

    def _tree_r(self, path, prefix, lines):
        items = self.vfs.listdir(path)
        for idx, item in enumerate(items):
            full = path.rstrip("/")+"/"+item if path != "/" else "/"+item
            con  = "└── " if idx==len(items)-1 else "├── "
            lines.append(prefix+con+(item+"/" if self.vfs.is_dir(full) else item))
            if self.vfs.is_dir(full):
                self._tree_r(full, prefix+("    " if idx==len(items)-1 else "│   "), lines)

    # files
    def cmd_cat(self, args, stdin=None, **_):
        if stdin: return stdin
        if not args: return "cat: missing operand"
        out = []
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            try: out.append(self.vfs.read(path))
            except Exception as e: out.append(str(e))
        return "".join(out)

    def cmd_touch(self, args, **_):
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            if not self.vfs.exists(path):
                try: self.vfs.write(path, "")
                except Exception as e: return str(e)

    def cmd_mkfile(self, args, **_):
        if not args: return "mkfile: usage: mkfile <file> [content...]"
        path = self.vfs.resolve(args[0], self.cwd)
        content = " ".join(args[1:]) if len(args)>1 else ""
        try: self.vfs.write(path, content+("\n" if content else "")); return f"Created: {path}"
        except Exception as e: return str(e)

    def cmd_mkdir(self, args, **_):
        if not args: return "mkdir: missing operand"
        for a in args:
            path = self.vfs.resolve(a, self.cwd)
            try: self.vfs.mkdir(path)
            except Exception as e: return str(e)

    def cmd_rm(self, args, **_):
        if not args: return "rm: missing operand"
        recursive = "-r" in args or "-rf" in args
        for a in [x for x in args if not x.startswith("-")]:
            path = self.vfs.resolve(a, self.cwd)
            try: self.vfs.remove(path, recursive=recursive)
            except Exception as e: return str(e)

    def cmd_cp(self, args, **_):
        if len(args)<2: return "cp: missing operand"
        try: self.vfs.copy(self.vfs.resolve(args[0],self.cwd), self.vfs.resolve(args[1],self.cwd))
        except Exception as e: return str(e)

    def cmd_mv(self, args, **_):
        if len(args)<2: return "mv: missing operand"
        try: self.vfs.move(self.vfs.resolve(args[0],self.cwd), self.vfs.resolve(args[1],self.cwd))
        except Exception as e: return str(e)

    def cmd_ln(self, args, **_):
        if len(args)<2: return "ln: usage: ln <src> <dst>"
        try: self.vfs.copy(self.vfs.resolve(args[0],self.cwd), self.vfs.resolve(args[1],self.cwd)); return f"Linked: {args[0]} → {args[1]}"
        except Exception as e: return str(e)

    def cmd_echo(self, args, **_):
        return " ".join(args).replace("\\n","\n").replace("\\t","\t")

    def cmd_write(self, args, **_):
        if len(args)<2: return "write: usage: write <file> <content...>"
        path = self.vfs.resolve(args[0], self.cwd)
        try: self.vfs.write(path, " ".join(args[1:]).replace("\\n","\n")+"\n")
        except Exception as e: return str(e)

    def cmd_head(self, args, **_):
        n=10; targets=[]; i=0
        while i<len(args):
            if args[i]=="-n" and i+1<len(args): n=int(args[i+1]); i+=2
            else: targets.append(args[i]); i+=1
        if not targets: return "head: missing file"
        out=[]
        for a in targets:
            try: out.append("\n".join(self.vfs.read(self.vfs.resolve(a,self.cwd)).splitlines()[:n]))
            except Exception as e: out.append(str(e))
        return "\n".join(out)

    def cmd_tail(self, args, **_):
        n=10; targets=[]; i=0
        while i<len(args):
            if args[i]=="-n" and i+1<len(args): n=int(args[i+1]); i+=2
            else: targets.append(args[i]); i+=1
        if not targets: return "tail: missing file"
        out=[]
        for a in targets:
            try: out.append("\n".join(self.vfs.read(self.vfs.resolve(a,self.cwd)).splitlines()[-n:]))
            except Exception as e: out.append(str(e))
        return "\n".join(out)

    def cmd_wc(self, args, stdin=None, **_):
        if stdin: text,label=stdin,""
        elif args:
            try: text=self.vfs.read(self.vfs.resolve(args[0],self.cwd)); label=args[0]
            except Exception as e: return str(e)
        else: return "wc: missing operand"
        return f"  {text.count(chr(10)):>6}  {len(text.split()):>6}  {len(text):>6}  {label}"

    def cmd_find(self, args, **_):
        path_arg = args[0] if args else self.cwd
        name_pat = None
        if "-name" in args:
            i=args.index("-name")
            if i+1<len(args): name_pat=args[i+1].replace("*","")
        base = self.vfs.resolve(path_arg, self.cwd)
        results = [k for k in self.vfs._tree if k.startswith(base) and (not name_pat or name_pat in k)]
        return "\n".join(sorted(results)) if results else "(no matches)"

    def cmd_stat(self, args, **_):
        if not args: return "stat: missing operand"
        out=[]
        for a in args:
            path=self.vfs.resolve(a,self.cwd)
            if not self.vfs.exists(path): out.append(f"stat: {a}: No such file or directory"); continue
            m=self.vfs.meta(path); kind="directory" if self.vfs.is_dir(path) else "regular file"
            out.append(f"  File: {path}\n  Type: {kind}\n  Size: {m.get('size',0) if self.vfs.is_file(path) else '-'} bytes\n  Created:  {m.get('created','?')}\n  Modified: {m.get('modified','?')}")
        return "\n".join(out)

    def cmd_chmod(self, args, **_):
        if len(args)<2: return "chmod: usage: chmod <mode> <file>"
        path=self.vfs.resolve(args[1],self.cwd)
        if not self.vfs.exists(path): return f"chmod: {args[1]}: No such file or directory"
        self.vfs._tree[path]["_meta"]["mode"]=args[0]
        return f"mode of '{args[1]}' changed to {args[0]}"

    # text
    def cmd_grep(self, args, stdin=None, **_):
        if not args: return "grep: usage: grep [-inv] <pattern> [file...]"
        ic="-i" in args; sn="-n" in args; iv="-v" in args
        clean=[a for a in args if not a.startswith("-")]
        if not clean: return "grep: missing pattern"
        try: rx=re.compile(clean[0], re.IGNORECASE if ic else 0)
        except re.error as e: return f"grep: invalid regex: {e}"
        def search(text, label=""):
            out=[]
            for i,line in enumerate(text.splitlines(),1):
                m=bool(rx.search(line))
                if iv: m=not m
                if m:
                    pre=f"{label}{i}:" if sn else (f"{label}" if label else "")
                    out.append(pre+line)
            return out
        if stdin and len(clean)==1:
            r=search(stdin); return "\n".join(r) if r else "(no matches)"
        files=clean[1:]
        if not files: return "grep: no files and no piped input"
        all_out=[]
        for f in files:
            try:
                text=self.vfs.read(self.vfs.resolve(f,self.cwd))
                all_out.extend(search(text, f"{f}:" if len(files)>1 else ""))
            except Exception as e: all_out.append(str(e))
        return "\n".join(all_out) if all_out else "(no matches)"

    def cmd_sort(self, args, stdin=None, **_):
        rev="-r" in args; uniq="-u" in args
        clean=[a for a in args if not a.startswith("-")]
        text=stdin if stdin else (self.vfs.read(self.vfs.resolve(clean[0],self.cwd)) if clean else None)
        if not text: return "sort: missing input"
        lines=sorted(text.splitlines(), reverse=rev)
        if uniq:
            seen=set(); lines=[l for l in lines if not (l in seen or seen.add(l))]
        return "\n".join(lines)

    def cmd_uniq(self, args, stdin=None, **_):
        cnt="-c" in args; clean=[a for a in args if not a.startswith("-")]
        text=stdin if stdin else (self.vfs.read(self.vfs.resolve(clean[0],self.cwd)) if clean else None)
        if not text: return "uniq: missing input"
        lines=text.splitlines(); out=[]; prev=None; c=0
        for line in lines:
            if line==prev: c+=1
            else:
                if prev is not None: out.append((f"{c:>4} " if cnt else "")+prev)
                prev,c=line,1
        if prev is not None: out.append((f"{c:>4} " if cnt else "")+prev)
        return "\n".join(out)

    def cmd_base64(self, args, stdin=None, **_):
        dec="-d" in args; clean=[a for a in args if not a.startswith("-")]
        text=stdin.strip() if stdin else (" ".join(clean) if clean else None)
        if not text: return "base64: usage: base64 [-d] <text>"
        try:
            return (_base64.b64decode(text.encode()).decode() if dec
                    else _base64.b64encode(text.encode()).decode())
        except Exception as e: return f"base64: error: {e}"

    def cmd_nano(self, args, **_):
        # GUI nano is handled separately via the editor window; stub here
        return "(Use File Manager → right-click → Edit, or double-click a file)"

    # process
    def cmd_ps(self, args, **_):
        rows=["  PID  NAME            OWNER    STATUS   STARTED","  "+"─"*48]
        for p in self.proc.list():
            rows.append(f"  {p['pid']:>4}  {p['name']:<15}  {p['owner']:<8} {p['status']}  {p['started']}")
        return "\n".join(rows)

    def cmd_kill(self, args, **_):
        if not args: return "kill: usage: kill <pid>"
        try: pid=int(args[0])
        except: return "kill: invalid PID"
        return f"Process {pid} terminated." if self.proc.kill(pid) else f"kill: ({pid}) — not permitted or not found"

    # env
    def cmd_env(self, args, **_):    return "\n".join(f"{k}={v}" for k,v in sorted(self.env.all().items()))
    def cmd_export(self, args, **_):
        for a in args:
            if "=" in a: k,v=a.split("=",1); self.env.set(k,v)
            else: return f"export: invalid syntax: {a}"
    def cmd_unset(self, args, **_):
        for a in args: self.env.unset(a)

    # system info
    def cmd_uname(self, args, **_):
        if "-a" in args:
            return f"PyOS pyos 2.0.0 #{random.randint(1000,9999)} SMP Python/{platform.python_version()} {platform.machine()}"
        return "PyOS"
    def cmd_uptime(self, args, **_):
        return f" {datetime.datetime.now().strftime('%H:%M:%S')} up forever,  1 user,  load average: 0.00, 0.00, 0.00"
    def cmd_free(self, args, **_):
        return "              total        used        free\nMem:          65536       12288       53248\nSwap:             0           0           0"
    def cmd_df(self, args, **_):
        total=sum(n.get("_meta",{}).get("size",0) for n in self.vfs._tree.values() if n.get("_type")=="file")
        return f"Filesystem          Size  Used  Avail  Use%  Mounted on\npyos-vfs           1024K  {total//1024}K   {(1024*1024-total)//1024}K    {total//(1024*10)}%   /"
    def cmd_ping(self, args, **_):
        if not args: return "ping: usage: ping <host> [-c <count>]"
        host=next((a for a in args if not a.startswith("-")),None)
        count=4
        if "-c" in args:
            i=args.index("-c")
            if i+1<len(args):
                try: count=int(args[i+1])
                except: pass
        rows=[f"  PING {host}: 56 data bytes"]
        for i in range(1,count+1): rows.append(f"  64 bytes from {host}: icmp_seq={i} ttl=64 time={round(random.uniform(0.5,80.0),3)} ms")
        rows.append(f"\n  --- {host} ping statistics ---")
        rows.append(f"  {count} packets transmitted, {count} received, 0% packet loss")
        return "\n".join(rows)

    # utilities
    def cmd_date(self, args, **_):    return datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Y")
    def cmd_whoami(self, args, **_):  return self.env.get("USER")
    def cmd_hostname(self, args, **_):return "pyos"
    def cmd_ver(self, args, **_):
        return f"  PyOS GUI v2.0\n  Python {platform.python_version()} on {platform.system()} {platform.machine()}\n  State file: {STATE_FILE}"
    def cmd_calc(self, args, **_):
        if not args: return "calc: usage: calc <expression>"
        expr=" ".join(args)
        if not all(c in "0123456789+-*/()., %" for c in expr): return "calc: unsafe characters"
        try: return f"{expr} = {eval(expr)}"  # noqa
        except Exception as e: return f"calc: {e}"
    def cmd_hash(self, args, **_):
        if not args: return "hash: usage: hash <text>"
        t=" ".join(args).encode()
        return f"  MD5:    {hashlib.md5(t).hexdigest()}\n  SHA256: {hashlib.sha256(t).hexdigest()}"
    def cmd_clear(self, args, **_):   return "\x0c"   # form-feed — GUI handles it
    def cmd_banner(self, args, **_):
        return r"""
  ____        ___  ____
 |  _ \ _   _/ _ \/ ___|
 | |_) | | | | | | \___ \
 |  __/| |_| | |_| |___) |
 |_|    \__, |\___/|____/
        |___/          v2.0  GUI
"""
    def cmd_history(self, args, **_):
        cmds=self.hist.all()
        if not cmds: return "(no history)"
        return "\n".join(f"  {i+1:>4}  {c}" for i,c in enumerate(cmds))
    def cmd_alias(self, args, **_):
        if not args:
            if not self._aliases: return "(no aliases)"
            return "\n".join(f"  {k}={v}" for k,v in self._aliases.items())
        for a in args:
            if "=" in a: k,v=a.split("=",1); self._aliases[k]=v
            else: return f"alias: invalid syntax: {a}"
    def cmd_unalias(self, args, **_):
        for a in args: self._aliases.pop(a,None)
    def cmd_which(self, args, **_):
        if not args: return "which: usage: which <command>"
        out=[]
        for cmd in args:
            if hasattr(self,f"cmd_{cmd}"): out.append(f"  {cmd}: built-in pysh command")
            elif cmd in self._aliases:      out.append(f"  {cmd}: alias → {self._aliases[cmd]}")
            else:                           out.append(f"  {cmd}: not found")
        return "\n".join(out)
    def cmd_man(self, args, **_):
        pages = {
            "ls":"ls [-l] [-a] [path]\n  List directory contents.",
            "cd":"cd [path]\n  Change directory.",
            "grep":"grep [-i] [-n] [-v] <pattern> [file...]\n  Regex search.",
            "calc":"calc <expression>\n  Arithmetic calculator.",
            "note":"note [add <text>|list|del <id>|clear]\n  Persistent quick notes.",
            "cron":"cron [add <secs> <cmd>|list|del <id>]\n  Scheduled commands.",
            "nano":"nano <file>\n  Opens the GUI text editor for that file.",
            "find":"find [path] [-name <pat>]\n  Search VFS.",
            "stat":"stat <file|dir>\n  Show metadata.",
            "hash":"hash <text>\n  MD5 + SHA256.",
            "ping":"ping <host> [-c <count>]\n  Simulated ping.",
            "save":"save\n  Manually persist state.",
            "reset":"reset\n  Wipe all saved state.",
        }
        if not args: return "man: usage: man <command>"
        cmd=args[0]
        if cmd in pages: return f"\n  MAN: {cmd}\n  {'─'*38}\n" + "\n".join("  "+l for l in pages[cmd].splitlines()) + f"\n  {'─'*38}"
        return f"man: no manual entry for '{cmd}'"

    # notes
    def cmd_note(self, args, **_):
        sub=args[0] if args else "list"
        if sub=="add":
            if len(args)<2: return "note: usage: note add <text>"
            self._notes.append({"id":len(self._notes)+1,"ts":datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),"text":" ".join(args[1:])})
            return f"  Note #{len(self._notes)} added."
        elif sub=="list":
            if not self._notes: return "  (no notes)"
            return "\n".join(f"  {n['id']:>2}  {n['ts']}  {n['text']}" for n in self._notes)
        elif sub=="del":
            if len(args)<2: return "note: usage: note del <id>"
            try: nid=int(args[1])
            except: return "note: invalid id"
            before=len(self._notes); self._notes=[n for n in self._notes if n["id"]!=nid]
            return f"  Note #{nid} deleted." if len(self._notes)<before else f"  Note #{nid} not found."
        elif sub=="clear":
            self._notes=[]; return "  All notes cleared."
        return f"note: unknown subcommand: {sub}"

    # cron
    def cmd_cron(self, args, **_):
        sub=args[0] if args else "list"
        if sub=="add":
            if len(args)<3: return "cron: usage: cron add <secs> <cmd>"
            try: interval=int(args[1])
            except: return "cron: interval must be integer"
            entry={"id":len(self._cron)+1,"interval":interval,"cmd":" ".join(args[2:]),"last":0}
            self._cron.append(entry); return f"  Cron job #{entry['id']} added: every {interval}s → {entry['cmd']}"
        elif sub=="list":
            if not self._cron: return "  (no cron jobs)"
            return "\n".join(f"  {j['id']:>2}  {j['interval']:>6}s  {j['cmd']}" for j in self._cron)
        elif sub=="del":
            if len(args)<2: return "cron: usage: cron del <id>"
            try: jid=int(args[1])
            except: return "cron: invalid id"
            before=len(self._cron); self._cron=[j for j in self._cron if j["id"]!=jid]
            return f"  Cron job #{jid} removed." if len(self._cron)<before else f"  Job #{jid} not found."
        return f"cron: unknown subcommand: {sub}"

    def run_cron(self):
        now=time.time()
        for job in self._cron:
            if now-job.get("last",0)>=job["interval"]:
                job["last"]=now; self.run_line(job["cmd"])

    # persistence cmds
    def cmd_save(self, args, **_):  self._save_state(); return f"  State saved → {STATE_FILE}"
    def cmd_load(self, args, **_):  self._load_state(); return f"  State reloaded ← {STATE_FILE}"
    def cmd_reset(self, args, **_):
        try: os.remove(STATE_FILE)
        except: pass
        return "  State wiped. Restart to begin fresh."

    # user management
    def cmd_adduser(self, args, **_):
        if not args: return "adduser: usage: adduser <username>"
        name=args[0]
        if name in self._users: return f"adduser: user '{name}' already exists"
        self._users[name]={"password":hashlib.sha256(b"").hexdigest(),"home":f"/home/{name}"}
        try: self.vfs.mkdir(f"/home/{name}")
        except: pass
        return f"User '{name}' created."
    def cmd_passwd(self, args, **_):
        return "(Use the GUI Users panel to change passwords)"
    def cmd_users(self, args, **_):
        rows=["  USER            HOME","  "+"─"*30]
        rows+=[f"  {u:<15}  {info.get('home','?')}" for u,info in self._users.items()]
        return "\n".join(rows)

# ─────────────────────────────────────────────────────────────────────────────
#  GUI APPLICATION
# ─────────────────────────────────────────────────────────────────────────────
class PyOSApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PyOS GUI v2.0")
        self.root.configure(bg=PAL["bg"])
        self.root.minsize(1000, 620)

        # shell engine
        self.shell = Shell(on_output=self._term_write, on_refresh=self._refresh_all)

        self._hist_idx = -1
        self._hist_draft = ""

        self._build_ui()
        self._refresh_all()
        self._term_banner()

        # cron ticker
        self._tick_cron()

    # ─────────────────────────────────────────
    #  UI CONSTRUCTION
    # ─────────────────────────────────────────
    def _build_ui(self):
        self._build_menubar()
        self._build_titlebar()

        # main 3-column layout
        main = tk.Frame(self.root, bg=PAL["bg"])
        main.pack(fill=tk.BOTH, expand=True)

        # LEFT: file manager sidebar
        self._build_sidebar(main)

        # CENTRE: terminal
        self._build_terminal(main)

        # RIGHT: info panel
        self._build_info_panel(main)

        # BOTTOM: status bar
        self._build_statusbar()

    def _build_menubar(self):
        mb = tk.Menu(self.root, bg=PAL["panel"], fg=PAL["fg"],
                     activebackground=PAL["sel"], activeforeground=PAL["fg"],
                     relief=tk.FLAT, bd=0)
        self.root.config(menu=mb)

        # File
        fm = tk.Menu(mb, tearoff=0, bg=PAL["panel"], fg=PAL["fg"],
                     activebackground=PAL["sel"], activeforeground=PAL["fg"])
        fm.add_command(label="New File",      command=self._menu_new_file)
        fm.add_command(label="New Directory", command=self._menu_new_dir)
        fm.add_separator()
        fm.add_command(label="Save State",    command=lambda: self.shell.cmd_save([]))
        fm.add_command(label="Reset State",   command=self._menu_reset)
        fm.add_separator()
        fm.add_command(label="Quit",          command=self._quit)
        mb.add_cascade(label="File", menu=fm)

        # Edit
        em = tk.Menu(mb, tearoff=0, bg=PAL["panel"], fg=PAL["fg"],
                     activebackground=PAL["sel"], activeforeground=PAL["fg"])
        em.add_command(label="Clear Terminal", command=self._clear_terminal)
        em.add_command(label="Copy Selection", command=lambda: self.root.focus_get().event_generate("<<Copy>>"))
        mb.add_cascade(label="Edit", menu=em)

        # View
        vm = tk.Menu(mb, tearoff=0, bg=PAL["panel"], fg=PAL["fg"],
                     activebackground=PAL["sel"], activeforeground=PAL["fg"])
        vm.add_command(label="Refresh File Tree", command=self._refresh_tree)
        vm.add_command(label="Show Notes",        command=self._open_notes_win)
        vm.add_command(label="Show Processes",    command=self._open_ps_win)
        vm.add_command(label="Show Cron Jobs",    command=self._open_cron_win)
        mb.add_cascade(label="View", menu=vm)

        # Help
        hm = tk.Menu(mb, tearoff=0, bg=PAL["panel"], fg=PAL["fg"],
                     activebackground=PAL["sel"], activeforeground=PAL["fg"])
        hm.add_command(label="Command Help", command=lambda: self.shell.run_line("help"))
        hm.add_command(label="About PyOS",   command=self._about)
        mb.add_cascade(label="Help", menu=hm)

    def _build_titlebar(self):
        bar = tk.Frame(self.root, bg=PAL["header"], height=36)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        # traffic-light dots
        dot_frame = tk.Frame(bar, bg=PAL["header"])
        dot_frame.pack(side=tk.LEFT, padx=10)
        for col, cmd in [(PAL["red"], self._quit),
                         (PAL["yellow"], lambda: self.root.iconify()),
                         (PAL["green"], lambda: None)]:
            d = tk.Label(dot_frame, bg=col, width=2, cursor="hand2")
            d.pack(side=tk.LEFT, padx=2, pady=8)
            d.bind("<Button-1>", lambda e, c=cmd: c())

        tk.Label(bar, text="⬡  PyOS GUI v2.0", bg=PAL["header"],
                 fg=PAL["accent"], font=("Helvetica", 13, "bold")).pack(side=tk.LEFT, padx=8)

        # clock
        self._clock_var = tk.StringVar()
        tk.Label(bar, textvariable=self._clock_var, bg=PAL["header"],
                 fg=PAL["fg_dim"], font=("Helvetica", 11)).pack(side=tk.RIGHT, padx=14)
        self._update_clock()

    def _build_sidebar(self, parent):
        side = tk.Frame(parent, bg=PAL["panel"], width=210)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)

        # header
        tk.Label(side, text="  📁  File Manager", bg=PAL["header"],
                 fg=PAL["accent"], font=("Helvetica", 11, "bold"),
                 anchor="w").pack(fill=tk.X)

        # quick-nav buttons
        nav = tk.Frame(side, bg=PAL["panel"])
        nav.pack(fill=tk.X, pady=(4,0))
        for label, path in [("🏠 Home", "/home/user"), ("📄 Docs", "/home/user/Documents"),
                             ("⬇  Downloads", "/home/user/Downloads"),
                             ("🗂 /etc", "/etc"), ("📋 /var/log", "/var/log"),
                             ("📦 /tmp", "/tmp")]:
            btn = tk.Label(nav, text=label, bg=PAL["panel"], fg=PAL["fg"],
                           anchor="w", padx=12, cursor="hand2",
                           font=("Helvetica", 10))
            btn.pack(fill=tk.X)
            btn.bind("<Button-1>", lambda e, p=path: self._nav_to(p))
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=PAL["btn_h"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=PAL["panel"]))

        tk.Frame(side, bg=PAL["border"], height=1).pack(fill=tk.X, pady=4)

        # tree
        tree_frame = tk.Frame(side, bg=PAL["panel"])
        tree_frame.pack(fill=tk.BOTH, expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("PyOS.Treeview",
            background=PAL["panel"], foreground=PAL["fg"],
            fieldbackground=PAL["panel"], borderwidth=0,
            font=("Courier", 10), rowheight=22)
        style.configure("PyOS.Treeview.Heading",
            background=PAL["header"], foreground=PAL["fg_dim"],
            font=("Helvetica", 9, "bold"), relief="flat")
        style.map("PyOS.Treeview",
            background=[("selected", PAL["sel"])],
            foreground=[("selected", PAL["fg"])])

        self.tree = ttk.Treeview(tree_frame, style="PyOS.Treeview",
                                  show="tree", selectmode="browse")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>",          self._on_tree_double)
        self.tree.bind("<Button-3>",          self._tree_context_menu)

    def _build_terminal(self, parent):
        term_frame = tk.Frame(parent, bg=PAL["bg"])
        term_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # tab bar
        tab_bar = tk.Frame(term_frame, bg=PAL["header"], height=30)
        tab_bar.pack(fill=tk.X)
        tab_bar.pack_propagate(False)
        tk.Label(tab_bar, text="  >_  Terminal", bg=PAL["sel"],
                 fg=PAL["fg"], font=("Helvetica", 10, "bold"),
                 padx=12).pack(side=tk.LEFT, fill=tk.Y)

        # output area
        mono = ("Courier New", 11) if platform.system()=="Windows" else ("Courier", 11)

        out_frame = tk.Frame(term_frame, bg=PAL["term_bg"])
        out_frame.pack(fill=tk.BOTH, expand=True)

        self.term_out = tk.Text(
            out_frame,
            bg=PAL["term_bg"], fg=PAL["term_fg"],
            font=mono, insertbackground=PAL["accent"],
            selectbackground=PAL["sel"], selectforeground=PAL["fg"],
            wrap=tk.WORD, relief=tk.FLAT, bd=8,
            state=tk.DISABLED, cursor="arrow"
        )
        vscroll = ttk.Scrollbar(out_frame, orient=tk.VERTICAL, command=self.term_out.yview)
        self.term_out.configure(yscrollcommand=vscroll.set)
        self.term_out.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vscroll.pack(side=tk.RIGHT, fill=tk.Y)

        # colour tags
        self.term_out.tag_config("prompt",  foreground=PAL["green"],  font=(mono[0], mono[1], "bold"))
        self.term_out.tag_config("output",  foreground=PAL["fg"])
        self.term_out.tag_config("error",   foreground=PAL["red"])
        self.term_out.tag_config("info",    foreground=PAL["cyan"])
        self.term_out.tag_config("dim",     foreground=PAL["fg_dim"])
        self.term_out.tag_config("banner",  foreground=PAL["accent"], font=(mono[0], mono[1], "bold"))
        self.term_out.tag_config("success", foreground=PAL["green"])
        self.term_out.tag_config("warn",    foreground=PAL["yellow"])

        # input row
        in_frame = tk.Frame(term_frame, bg=PAL["panel"], pady=4)
        in_frame.pack(fill=tk.X)

        self._prompt_var = tk.StringVar()
        self._prompt_label = tk.Label(in_frame, textvariable=self._prompt_var,
            bg=PAL["panel"], fg=PAL["green"],
            font=(mono[0], mono[1], "bold"), padx=6)
        self._prompt_label.pack(side=tk.LEFT)

        self.term_in = tk.Entry(in_frame, bg=PAL["input_bg"], fg=PAL["fg"],
            insertbackground=PAL["accent"], selectbackground=PAL["sel"],
            font=mono, relief=tk.FLAT, bd=4)
        self.term_in.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0,6))
        self.term_in.focus_set()
        self.term_in.bind("<Return>",   self._on_enter)
        self.term_in.bind("<Up>",       self._hist_up)
        self.term_in.bind("<Down>",     self._hist_down)
        self.term_in.bind("<Tab>",      self._tab_complete)

    def _build_info_panel(self, parent):
        info = tk.Frame(parent, bg=PAL["panel"], width=200)
        info.pack(side=tk.RIGHT, fill=tk.Y)
        info.pack_propagate(False)

        tk.Label(info, text="  ℹ  System Info", bg=PAL["header"],
                 fg=PAL["accent"], font=("Helvetica", 11, "bold"),
                 anchor="w").pack(fill=tk.X)

        self._info_text = tk.Text(info, bg=PAL["panel"], fg=PAL["fg_dim"],
            font=("Courier", 9), relief=tk.FLAT, bd=6,
            state=tk.DISABLED, wrap=tk.WORD, cursor="arrow")
        self._info_text.pack(fill=tk.BOTH, expand=True)

        # notes mini-panel
        tk.Frame(info, bg=PAL["border"], height=1).pack(fill=tk.X)
        tk.Label(info, text="  📌 Notes", bg=PAL["header"],
                 fg=PAL["yellow"], font=("Helvetica", 10, "bold"),
                 anchor="w").pack(fill=tk.X)

        note_frame = tk.Frame(info, bg=PAL["panel"])
        note_frame.pack(fill=tk.X, padx=6, pady=4)

        self._note_entry = tk.Entry(note_frame, bg=PAL["input_bg"], fg=PAL["fg"],
            insertbackground=PAL["accent"], font=("Helvetica", 9),
            relief=tk.FLAT, bd=3)
        self._note_entry.pack(fill=tk.X, side=tk.LEFT, expand=True)
        self._note_entry.bind("<Return>", self._quick_note)

        tk.Button(note_frame, text="+", bg=PAL["btn"], fg=PAL["green"],
            relief=tk.FLAT, command=self._quick_note, cursor="hand2",
            font=("Helvetica", 10, "bold")).pack(side=tk.RIGHT)

        self._notes_list = tk.Listbox(info, bg=PAL["panel"], fg=PAL["fg"],
            font=("Helvetica", 9), relief=tk.FLAT, bd=0,
            selectbackground=PAL["sel"], activestyle="none", height=6)
        self._notes_list.pack(fill=tk.BOTH, expand=True, padx=4)
        self._notes_list.bind("<Double-1>", self._delete_note)

        # action buttons
        tk.Frame(info, bg=PAL["border"], height=1).pack(fill=tk.X, pady=2)
        btn_frame = tk.Frame(info, bg=PAL["panel"])
        btn_frame.pack(fill=tk.X, padx=6, pady=4)
        for label, cmd in [("💾 Save", lambda: self._run_and_echo("save")),
                           ("🗑 Clear", self._clear_terminal),
                           ("📋 PS",    self._open_ps_win),
                           ("⏰ Cron",  self._open_cron_win)]:
            b = tk.Button(btn_frame, text=label, bg=PAL["btn"], fg=PAL["fg"],
                relief=tk.FLAT, cursor="hand2", command=cmd,
                font=("Helvetica", 9), pady=3)
            b.pack(fill=tk.X, pady=1)
            b.bind("<Enter>", lambda e, x=b: x.config(bg=PAL["btn_h"]))
            b.bind("<Leave>", lambda e, x=b: x.config(bg=PAL["btn"]))

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PAL["header"], height=22)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self._status_var = tk.StringVar(value="Ready")
        tk.Label(bar, textvariable=self._status_var,
                 bg=PAL["header"], fg=PAL["fg_dim"],
                 font=("Helvetica", 9), anchor="w", padx=8).pack(side=tk.LEFT)

        self._cwd_var = tk.StringVar()
        tk.Label(bar, textvariable=self._cwd_var,
                 bg=PAL["header"], fg=PAL["accent"],
                 font=("Courier", 9), anchor="e", padx=8).pack(side=tk.RIGHT)

        self._save_ind = tk.Label(bar, text="● saved", bg=PAL["header"],
                                   fg=PAL["green"], font=("Helvetica", 9), padx=8)
        self._save_ind.pack(side=tk.RIGHT)

    # ─────────────────────────────────────────
    #  TERMINAL I/O
    # ─────────────────────────────────────────
    def _term_write(self, text, tag="output"):
        self.term_out.config(state=tk.NORMAL)
        if text == "\x0c":          # form-feed = clear
            self.term_out.delete("1.0", tk.END)
        else:
            # auto-tag based on content keywords
            if tag == "output":
                low = text.lower()
                if any(w in low for w in ("error","no such","not found","missing","cannot","invalid","failed","denied")):
                    tag = "error"
                elif any(w in low for w in ("saved","created","linked","added","terminated","updated","wiped")):
                    tag = "success"
                elif any(w in low for w in ("warning","caution","deprecated")):
                    tag = "warn"
            self.term_out.insert(tk.END, text + ("\n" if not text.endswith("\n") else ""), tag)
        self.term_out.config(state=tk.DISABLED)
        self.term_out.see(tk.END)

    def _term_banner(self):
        banner = r"""
  ____        ___  ____
 |  _ \ _   _/ _ \/ ___|
 | |_) | | | | | | \___ \
 |  __/| |_| | |_| |___) |
 |_|    \__, |\___/|____/
        |___/          v2.0  GUI
"""
        self._term_write(banner, "banner")
        self._term_write("  Type 'help' for commands. Double-click files to edit them.\n", "dim")
        try:
            motd = self.shell.vfs.read("/etc/motd").strip()
            self._term_write(f"  {motd}\n", "info")
        except: pass

    def _on_enter(self, event=None):
        line = self.term_in.get().strip()
        if not line: return
        self.term_in.delete(0, tk.END)
        self._hist_idx = -1

        # echo prompt+command
        self._term_write(self.shell.prompt_str(), "prompt")
        self._term_write(line + "\n", "dim")

        self._status_var.set(f"Running: {line}")
        self.root.update_idletasks()
        self.shell.run_line(line)
        self._status_var.set("Ready")

    def _run_and_echo(self, line):
        self.term_in.delete(0, tk.END)
        self._term_write(self.shell.prompt_str(), "prompt")
        self._term_write(line + "\n", "dim")
        self.shell.run_line(line)

    # ─────────────────────────────────────────
    #  HISTORY NAVIGATION
    # ─────────────────────────────────────────
    def _hist_up(self, event=None):
        hist = self.shell.hist.all()
        if not hist: return "break"
        if self._hist_idx == -1:
            self._hist_draft = self.term_in.get()
            self._hist_idx = len(hist) - 1
        elif self._hist_idx > 0:
            self._hist_idx -= 1
        self.term_in.delete(0, tk.END)
        self.term_in.insert(0, hist[self._hist_idx])
        return "break"

    def _hist_down(self, event=None):
        hist = self.shell.hist.all()
        if self._hist_idx == -1: return "break"
        if self._hist_idx < len(hist) - 1:
            self._hist_idx += 1
            self.term_in.delete(0, tk.END)
            self.term_in.insert(0, hist[self._hist_idx])
        else:
            self._hist_idx = -1
            self.term_in.delete(0, tk.END)
            self.term_in.insert(0, self._hist_draft)
        return "break"

    def _tab_complete(self, event=None):
        """Tab-complete filenames in the current directory."""
        line = self.term_in.get()
        parts = line.split()
        if not parts: return "break"
        prefix = parts[-1]
        try:
            items = self.shell.vfs.listdir(self.shell.cwd)
            matches = [i for i in items if i.startswith(prefix)]
            if len(matches) == 1:
                parts[-1] = matches[0]
                self.term_in.delete(0, tk.END)
                self.term_in.insert(0, " ".join(parts))
            elif len(matches) > 1:
                self._term_write("\n" + "  ".join(matches) + "\n", "dim")
        except: pass
        return "break"

    # ─────────────────────────────────────────
    #  FILE TREE
    # ─────────────────────────────────────────
    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        self._fill_tree("", "/")

    def _fill_tree(self, parent_id, path):
        try:
            items = self.shell.vfs.listdir(path)
        except: return
        for item in items:
            full = path.rstrip("/")+"/"+item if path != "/" else "/"+item
            is_dir = self.shell.vfs.is_dir(full)
            icon = "📁" if is_dir else "📄"
            iid = self.tree.insert(parent_id, tk.END,
                text=f" {icon} {item}",
                values=(full,),
                open=False)
            if is_dir:
                self._fill_tree(iid, full)

    def _on_tree_select(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        path = self.tree.item(sel[0], "values")[0]
        self._update_info_panel(path)

    def _on_tree_double(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        path = self.tree.item(sel[0], "values")[0]
        if self.shell.vfs.is_dir(path):
            self.shell.cwd = path
            self._refresh_prompt()
        elif self.shell.vfs.is_file(path):
            self._open_editor(path)

    def _tree_context_menu(self, event):
        sel = self.tree.identify_row(event.y)
        if not sel: return
        self.tree.selection_set(sel)
        path = self.tree.item(sel, "values")[0]
        is_file = self.shell.vfs.is_file(path)

        menu = tk.Menu(self.root, tearoff=0, bg=PAL["panel"], fg=PAL["fg"],
                       activebackground=PAL["sel"], activeforeground=PAL["fg"])
        if is_file:
            menu.add_command(label="✏  Edit",   command=lambda: self._open_editor(path))
            menu.add_command(label="👁  View",   command=lambda: self._view_file(path))
            menu.add_separator()
        menu.add_command(label="🗑  Delete", command=lambda: self._delete_path(path))
        menu.add_command(label="📋  Copy path", command=lambda: self._copy_to_clipboard(path))
        if self.shell.vfs.is_dir(path):
            menu.add_command(label="📁  New file here", command=lambda: self._new_file_in(path))
            menu.add_command(label="📂  New dir here",  command=lambda: self._new_dir_in(path))
            menu.add_command(label="→  cd here",        command=lambda: self._nav_to(path))
        menu.tk_popup(event.x_root, event.y_root)

    def _nav_to(self, path):
        if self.shell.vfs.is_dir(path):
            self.shell.cwd = path
            self._refresh_all()
            self._run_and_echo(f"ls {path}")

    # ─────────────────────────────────────────
    #  EDITOR WINDOW
    # ─────────────────────────────────────────
    def _open_editor(self, path):
        win = tk.Toplevel(self.root)
        win.title(f"✏  nano — {path}")
        win.configure(bg=PAL["bg"])
        win.geometry("720x480")

        mono = ("Courier New", 11) if platform.system()=="Windows" else ("Courier", 11)

        # toolbar
        tb = tk.Frame(win, bg=PAL["header"])
        tb.pack(fill=tk.X)
        tk.Label(tb, text=f"  {path}", bg=PAL["header"], fg=PAL["accent"],
                 font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=6)

        def save_file():
            content = editor.get("1.0", tk.END)
            try:
                self.shell.vfs.write(path, content)
                self.shell._save_state()
                status.config(text="Saved ✓", fg=PAL["green"])
                self._refresh_all()
            except Exception as e:
                status.config(text=f"Error: {e}", fg=PAL["red"])

        tk.Button(tb, text="💾 Save", bg=PAL["btn"], fg=PAL["green"],
                  relief=tk.FLAT, command=save_file, cursor="hand2",
                  font=("Helvetica", 9, "bold"), padx=10).pack(side=tk.RIGHT, pady=3, padx=4)
        tk.Button(tb, text="✖ Close", bg=PAL["btn"], fg=PAL["fg_dim"],
                  relief=tk.FLAT, command=win.destroy, cursor="hand2",
                  font=("Helvetica", 9), padx=10).pack(side=tk.RIGHT, pady=3)

        status = tk.Label(tb, text="Editing", bg=PAL["header"], fg=PAL["fg_dim"],
                          font=("Helvetica", 9))
        status.pack(side=tk.RIGHT, padx=10)

        # editor + line numbers
        ed_frame = tk.Frame(win, bg=PAL["bg"])
        ed_frame.pack(fill=tk.BOTH, expand=True)

        line_nums = tk.Text(ed_frame, width=4, bg=PAL["panel"], fg=PAL["dim"],
                            font=mono, state=tk.DISABLED, relief=tk.FLAT,
                            bd=4, wrap=tk.NONE)
        line_nums.pack(side=tk.LEFT, fill=tk.Y)

        editor = tk.Text(ed_frame, bg=PAL["term_bg"], fg=PAL["fg"],
                         font=mono, insertbackground=PAL["accent"],
                         selectbackground=PAL["sel"], relief=tk.FLAT, bd=6,
                         wrap=tk.NONE, undo=True)
        scr_y = ttk.Scrollbar(ed_frame, orient=tk.VERTICAL, command=editor.yview)
        scr_x = ttk.Scrollbar(win, orient=tk.HORIZONTAL, command=editor.xview)
        editor.configure(yscrollcommand=scr_y.set, xscrollcommand=scr_x.set)
        scr_y.pack(side=tk.RIGHT, fill=tk.Y)
        editor.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scr_x.pack(fill=tk.X)

        # load content
        try: content = self.shell.vfs.read(path)
        except: content = ""
        editor.insert("1.0", content)

        def update_line_nums(event=None):
            line_nums.config(state=tk.NORMAL)
            line_nums.delete("1.0", tk.END)
            total = int(editor.index(tk.END).split(".")[0])
            line_nums.insert("1.0", "\n".join(str(i) for i in range(1, total)))
            line_nums.config(state=tk.DISABLED)
            status.config(text=f"Line {editor.index(tk.INSERT).split('.')[0]}", fg=PAL["fg_dim"])

        editor.bind("<KeyRelease>", update_line_nums)
        editor.bind("<Control-s>",  lambda e: save_file())
        update_line_nums()

    def _view_file(self, path):
        win = tk.Toplevel(self.root)
        win.title(f"👁  {path}")
        win.configure(bg=PAL["bg"])
        win.geometry("680x420")
        mono = ("Courier New", 10) if platform.system()=="Windows" else ("Courier", 10)
        txt = tk.Text(win, bg=PAL["term_bg"], fg=PAL["fg"], font=mono,
                      relief=tk.FLAT, bd=8, state=tk.DISABLED, wrap=tk.WORD)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.config(state=tk.NORMAL)
        try: txt.insert("1.0", self.shell.vfs.read(path))
        except Exception as e: txt.insert("1.0", str(e))
        txt.config(state=tk.DISABLED)

    # ─────────────────────────────────────────
    #  INFO PANEL
    # ─────────────────────────────────────────
    def _update_info_panel(self, path):
        if not self.shell.vfs.exists(path): return
        m = self.shell.vfs.meta(path)
        kind = "Directory" if self.shell.vfs.is_dir(path) else "File"
        lines = [
            f"  Path:\n  {path}\n",
            f"  Type: {kind}",
            f"  Size: {m.get('size','-')} bytes" if kind=="File" else "",
            f"  Created:\n  {m.get('created','?')}",
            f"  Modified:\n  {m.get('modified','?')}",
        ]
        self._info_text.config(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)
        self._info_text.insert("1.0", "\n".join(l for l in lines if l))
        self._info_text.config(state=tk.DISABLED)

    def _refresh_info_system(self):
        total_files = sum(1 for n in self.shell.vfs._tree.values() if n.get("_type")=="file")
        total_dirs  = sum(1 for n in self.shell.vfs._tree.values() if n.get("_type")=="dir")
        total_size  = sum(n.get("_meta",{}).get("size",0) for n in self.shell.vfs._tree.values() if n.get("_type")=="file")
        lines = [
            f"  OS: PyOS GUI v2.0",
            f"  Python: {platform.python_version()}",
            f"  Host: {platform.system()}",
            f"",
            f"  VFS:",
            f"  Files: {total_files}",
            f"  Dirs:  {total_dirs}",
            f"  Size:  {total_size} B",
            f"",
            f"  CWD:",
            f"  {self.shell.cwd}",
            f"",
            f"  User: {self.shell.env.get('USER')}",
            f"  Procs: {len(self.shell.proc.list())}",
            f"  Aliases: {len(self.shell._aliases)}",
            f"  Cron jobs: {len(self.shell._cron)}",
        ]
        self._info_text.config(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)
        self._info_text.insert("1.0", "\n".join(lines))
        self._info_text.config(state=tk.DISABLED)

    # ─────────────────────────────────────────
    #  NOTES PANEL
    # ─────────────────────────────────────────
    def _quick_note(self, event=None):
        text = self._note_entry.get().strip()
        if not text: return
        self._note_entry.delete(0, tk.END)
        self.shell.cmd_note(["add", text])
        self.shell._save_state()
        self._refresh_notes()

    def _refresh_notes(self):
        self._notes_list.delete(0, tk.END)
        for n in self.shell._notes:
            self._notes_list.insert(tk.END, f"#{n['id']} {n['text'][:28]}")

    def _delete_note(self, event=None):
        sel = self._notes_list.curselection()
        if not sel: return
        text = self._notes_list.get(sel[0])
        nid = int(text.split()[0].lstrip("#"))
        self.shell.cmd_note(["del", str(nid)])
        self.shell._save_state()
        self._refresh_notes()

    def _open_notes_win(self):
        win = tk.Toplevel(self.root)
        win.title("📌 Notes")
        win.configure(bg=PAL["bg"])
        win.geometry("460x360")
        tk.Label(win, text="  📌  PyOS Notes", bg=PAL["header"],
                 fg=PAL["yellow"], font=("Helvetica", 12, "bold"),
                 anchor="w").pack(fill=tk.X)
        lb = tk.Listbox(win, bg=PAL["panel"], fg=PAL["fg"],
                        font=("Courier", 10), relief=tk.FLAT, bd=8,
                        selectbackground=PAL["sel"], activestyle="none")
        lb.pack(fill=tk.BOTH, expand=True)
        for n in self.shell._notes:
            lb.insert(tk.END, f"  #{n['id']}  {n['ts']}  {n['text']}")

    # ─────────────────────────────────────────
    #  POPUP WINDOWS
    # ─────────────────────────────────────────
    def _open_ps_win(self):
        win = tk.Toplevel(self.root)
        win.title("⚙  Process Manager")
        win.configure(bg=PAL["bg"])
        win.geometry("500x300")
        tk.Label(win, text="  ⚙  Running Processes", bg=PAL["header"],
                 fg=PAL["accent"], font=("Helvetica", 11, "bold"),
                 anchor="w").pack(fill=tk.X)

        cols = ("PID","Name","Owner","Status","Started")
        tv = ttk.Treeview(win, columns=cols, show="headings", style="PyOS.Treeview")
        for c in cols:
            tv.heading(c, text=c)
            tv.column(c, width=80 if c!="Name" else 140)
        tv.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for p in self.shell.proc.list():
            tv.insert("", tk.END, values=(p["pid"],p["name"],p["owner"],p["status"],p["started"]))

        def kill_proc():
            sel = tv.selection()
            if not sel: return
            pid = int(tv.item(sel[0],"values")[0])
            result = self.shell.cmd_kill([str(pid)])
            self._term_write((result or "") + "\n", "output")
            tv.delete(sel[0])

        tk.Button(win, text="🗑  Kill Selected", bg=PAL["red"], fg=PAL["fg"],
                  relief=tk.FLAT, command=kill_proc, cursor="hand2",
                  font=("Helvetica", 10)).pack(pady=6)

    def _open_cron_win(self):
        win = tk.Toplevel(self.root)
        win.title("⏰  Cron Jobs")
        win.configure(bg=PAL["bg"])
        win.geometry("480x320")
        tk.Label(win, text="  ⏰  Cron Scheduler", bg=PAL["header"],
                 fg=PAL["cyan"], font=("Helvetica", 11, "bold"),
                 anchor="w").pack(fill=tk.X)

        lb = tk.Listbox(win, bg=PAL["panel"], fg=PAL["fg"],
                        font=("Courier", 10), relief=tk.FLAT, bd=8,
                        selectbackground=PAL["sel"], activestyle="none")
        lb.pack(fill=tk.BOTH, expand=True)
        for j in self.shell._cron:
            lb.insert(tk.END, f"  #{j['id']}  every {j['interval']}s  →  {j['cmd']}")

        add_frame = tk.Frame(win, bg=PAL["panel"])
        add_frame.pack(fill=tk.X, padx=8, pady=4)
        tk.Label(add_frame, text="Interval (s):", bg=PAL["panel"], fg=PAL["fg"],
                 font=("Helvetica", 9)).pack(side=tk.LEFT)
        int_e = tk.Entry(add_frame, width=6, bg=PAL["input_bg"], fg=PAL["fg"],
                         relief=tk.FLAT, bd=3)
        int_e.pack(side=tk.LEFT, padx=4)
        tk.Label(add_frame, text="Command:", bg=PAL["panel"], fg=PAL["fg"],
                 font=("Helvetica", 9)).pack(side=tk.LEFT)
        cmd_e = tk.Entry(add_frame, bg=PAL["input_bg"], fg=PAL["fg"],
                         relief=tk.FLAT, bd=3)
        cmd_e.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)

        def add_job():
            result = self.shell.cmd_cron(["add", int_e.get(), *cmd_e.get().split()])
            self._term_write((result or "") + "\n", "output")
            lb.insert(tk.END, f"  #{len(self.shell._cron)}  every {int_e.get()}s  →  {cmd_e.get()}")
            int_e.delete(0, tk.END); cmd_e.delete(0, tk.END)

        tk.Button(add_frame, text="Add", bg=PAL["btn"], fg=PAL["green"],
                  relief=tk.FLAT, command=add_job, cursor="hand2").pack(side=tk.RIGHT)

    # ─────────────────────────────────────────
    #  FILE OPS FROM MENU / TREE
    # ─────────────────────────────────────────
    def _menu_new_file(self):
        name = simpledialog.askstring("New File", "File name:", parent=self.root)
        if not name: return
        path = self.shell.vfs.resolve(name, self.shell.cwd)
        try:
            self.shell.vfs.write(path, "")
            self.shell._save_state()
            self._refresh_all()
            self._open_editor(path)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _menu_new_dir(self):
        name = simpledialog.askstring("New Directory", "Directory name:", parent=self.root)
        if not name: return
        path = self.shell.vfs.resolve(name, self.shell.cwd)
        try:
            self.shell.vfs.mkdir(path)
            self.shell._save_state()
            self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _new_file_in(self, dir_path):
        name = simpledialog.askstring("New File", "File name:", parent=self.root)
        if not name: return
        path = dir_path.rstrip("/")+"/"+name
        try:
            self.shell.vfs.write(path, "")
            self.shell._save_state(); self._refresh_all()
            self._open_editor(path)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _new_dir_in(self, dir_path):
        name = simpledialog.askstring("New Directory", "Directory name:", parent=self.root)
        if not name: return
        path = dir_path.rstrip("/")+"/"+name
        try:
            self.shell.vfs.mkdir(path)
            self.shell._save_state(); self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _delete_path(self, path):
        if not messagebox.askyesno("Delete", f"Delete '{path}'?", parent=self.root): return
        try:
            self.shell.vfs.remove(path, recursive=True)
            self.shell._save_state(); self._refresh_all()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _copy_to_clipboard(self, text):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def _menu_reset(self):
        if messagebox.askyesno("Reset", "Wipe ALL saved state? This cannot be undone.", parent=self.root):
            self.shell.cmd_reset([])
            messagebox.showinfo("Reset", "State wiped. Restart PyOS to begin fresh.")

    # ─────────────────────────────────────────
    #  REFRESH / HELPERS
    # ─────────────────────────────────────────
    def _refresh_all(self):
        self._refresh_tree()
        self._refresh_notes()
        self._refresh_info_system()
        self._refresh_prompt()
        self._cwd_var.set(f"cwd: {self.shell.cwd}")

    def _refresh_prompt(self):
        self._prompt_var.set(self.shell.prompt_str())

    def _clear_terminal(self):
        self.term_out.config(state=tk.NORMAL)
        self.term_out.delete("1.0", tk.END)
        self.term_out.config(state=tk.DISABLED)

    def _update_clock(self):
        self._clock_var.set(datetime.datetime.now().strftime("  %a %d %b  %H:%M:%S  "))
        self.root.after(1000, self._update_clock)

    def _tick_cron(self):
        self.shell.run_cron()
        self.root.after(5000, self._tick_cron)   # check every 5s

    def _about(self):
        messagebox.showinfo("About PyOS GUI",
            "PyOS GUI v2.0\n\nA desktop-style OS simulator built entirely in Python + tkinter.\n\n"
            "Features:\n• Virtual File System with persistence\n• Full terminal with 40+ commands\n"
            "• GUI text editor (nano)\n• File manager with context menu\n• Notes, Cron scheduler\n"
            "• Process manager\n• Dark theme\n\nNo external libraries required.",
            parent=self.root)

    def _quit(self):
        self.shell._save_state()
        self.root.destroy()

# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────
def main():
    try:
        import tkinter as tk
    except ImportError:
        print("ERROR: tkinter is not installed.")
        print("Install it with:")
        print("  Ubuntu/Debian:  sudo apt install python3-tk")
        print("  Fedora:         sudo dnf install python3-tkinter")
        print("  macOS:          brew install python-tk")
        print("  Windows:        Reinstall Python and check 'tcl/tk' option")
        sys.exit(1)

    root = tk.Tk()

    # DPI scaling
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    root.geometry("1200x720")
    root.resizable(True, True)

    # window icon (coloured square fallback)
    try:
        img = tk.PhotoImage(width=32, height=32)
        img.put(PAL["accent"], to=(0,0,31,31))
        root.iconphoto(True, img)
    except: pass

    app = PyOSApp(root)
    root.protocol("WM_DELETE_WINDOW", app._quit)
    root.mainloop()

if __name__ == "__main__":
    main()
