import glob, sys, os, platform
from pathlib import Path
IS_WIN = os.name == "nt"
def _setup_console():
    """UTF-8 output and ANSI colors on Windows Terminal / PowerShell / cmd."""
    for st in (sys.stdout, sys.stderr):
        try: st.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass
    if IS_WIN:
        try:
            import ctypes
            k = ctypes.windll.kernel32
            k.SetConsoleOutputCP(65001); k.SetConsoleCP(65001)
            h = k.GetStdHandle(-11); mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)): k.SetConsoleMode(h, mode.value | 0x0004)
        except Exception: pass
_setup_console()
if any(a in ("-h", "--help") for a in sys.argv[1:]):
    print("Forge - a local, offline personal AI assistant in your terminal (Ollama).\n"
          "Usage: python forge.py   (Windows: py forge.py)\n"
          "Set your name with FORGE_USER=Name or ~/.forge/config.json {\"user_name\": \"Name\"}.\n"
          "Inside Forge type / for the command menu, /help for help, /bye to quit.")
    sys.exit(0)
_SERVER_ENV = dict(os.environ)
# OLLAMA_HOST=0.0.0.0 is fine for the server but not as an address to connect to (WinError 10049 on Windows)
_oh = os.environ.get("OLLAMA_HOST", "")
if _oh.replace("http://", "").startswith("0.0.0.0"): os.environ["OLLAMA_HOST"] = _oh.replace("0.0.0.0", "127.0.0.1")
import ollama, json, os, re, datetime, threading, time, subprocess, shutil, urllib.request, urllib.parse, html as htmlmod
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.text import Text
from rich.panel import Panel
from rich.console import Group
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style
TB_STYLE = Style.from_dict({'bottom-toolbar': 'noreverse bg:default fg:#888888',
    'completion-menu': 'bg:#2b2b2b fg:#dddddd', 'completion-menu.completion.current': 'bg:#ff8c42 fg:#000000 bold',
    'completion-menu.meta.completion': 'bg:#2b2b2b fg:#888888', 'completion-menu.meta.completion.current': 'bg:#ff8c42 fg:#000000'})
from prompt_toolkit.completion import Completer, Completion
CMDS = {"/help": "show all commands", "/clear": "start a fresh chat", "/model": "show/change models per role, /model suggest",
        "/undo": "undo my last file edit(s)", "/deep": "think step by step", "/run": "run a shell command (asks y/n)",
        "/search": "search this project's files", "/web": "search the internet", "/plan": "make a to-do list for a task",
        "/todo": "show the current to-do list", "/agent": "let me work on a task by myself (asks before changes)",
        "/read": "read and summarize a file", "/bye": "quit (chat is saved)"}
class CmdCompleter(Completer):
    def get_completions(self, doc, ev):
        t = doc.text_before_cursor
        if t.startswith("/") and " " not in t:
            for c, d in CMDS.items():
                if c.startswith(t): yield Completion(c, start_position=-len(t), display_meta=d)

import subprocess as _sp, urllib.request as _ur
HOME = Path.home()
FORGE_DIR = HOME / "Forge"
CONFIG_FILE = HOME / ".forge" / "config.json"
def load_config():
    try: return json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    except Exception: return {}
def save_config(**kv):
    cfg = load_config(); cfg.update(kv)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
def _load_user_name():
    name = os.environ.get("FORGE_USER", "").strip() or str(load_config().get("user_name", "")).strip()
    return name or "friend"
USER_NAME = _load_user_name()
def ollama_bin():
    found = shutil.which("ollama")
    if found: return found
    for c in ([Path(os.environ.get("LOCALAPPDATA", HOME / "AppData/Local")) / "Programs/Ollama/ollama.exe"] if IS_WIN
              else [HOME / ".local/ollama/bin/ollama", Path("/usr/local/bin/ollama"), Path("/opt/homebrew/bin/ollama")]):
        if c.exists(): return str(c)
    return "ollama"
def ensure_ollama():
    try: _ur.urlopen("http://127.0.0.1:11434/api/version", timeout=2); return
    except Exception: pass
    print("🔥 Starting Ollama...")
    log = open(HOME / ".ollama-serve.log", "a")
    try:
        if IS_WIN:
            _sp.Popen([ollama_bin(), "serve"], stdout=log, stderr=_sp.STDOUT, stdin=_sp.DEVNULL, env=_SERVER_ENV,
                      creationflags=_sp.CREATE_NO_WINDOW | _sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP)
        else:
            _sp.Popen([ollama_bin(), "serve"], stdout=log, stderr=_sp.STDOUT, stdin=_sp.DEVNULL, env=_SERVER_ENV, start_new_session=True)
    except Exception as e:
        print(f"Could not start Ollama ({e}). Install it from https://ollama.com"); return
    for _ in range(30):
        time.sleep(0.5)
        try: _ur.urlopen("http://127.0.0.1:11434/api/version", timeout=2); return
        except Exception: pass
ensure_ollama()
console = Console()
DEFAULT_MODELS = {"chat": "qwen3:1.7b", "code": "qwen3:8b", "plan": "qwen3:1.7b"}
_cfgm = load_config().get("models", {})
CHAT_MODEL = _cfgm.get("chat", DEFAULT_MODELS["chat"])
SMART_MODEL = _cfgm.get("code", DEFAULT_MODELS["code"])
PLAN_MODEL = _cfgm.get("plan", DEFAULT_MODELS["plan"])
MEM_MODEL = CHAT_MODEL
CODE_WORDS = ("code","bug","error","function","script","python","c#","class","loop","variable","traceback")
EDIT_MODEL = SMART_MODEL
REASON_WORDS = ("why","how","explain","plan","compare","should","what if","difference","best","idea","think")
def route(msg, has_file):
    m = msg.lower()
    if has_file or any(w in m for w in CODE_WORDS): return SMART_MODEL, "code"
    if any(w in m for w in REASON_WORDS): return CHAT_MODEL, "reasoning"
    return CHAT_MODEL, "chat"
MEMDIR = str(FORGE_DIR / "memory")
BACKUP_DIR = str(FORGE_DIR / "backups")
for _d in ("memory", "backups", "tests"): (FORGE_DIR / _d).mkdir(parents=True, exist_ok=True)

OLD = str(HOME / "memories.json")
if os.path.exists(OLD) and not os.listdir(MEMDIR):
    with open(os.path.join(MEMDIR, "general.md"), "w", encoding="utf-8") as f:
        f.write("# general\n" + "".join("- " + m + "\n" for m in json.load(open(OLD, encoding="utf-8"))))

def load_mem():
    text = ""
    for name in sorted(os.listdir(MEMDIR)):
        if name.endswith(".md"):
            text += open(os.path.join(MEMDIR, name), encoding="utf-8", errors="replace").read() + "\n"
    return text

def save_mem(topic, fact):
    topic = re.sub(r"[^a-z0-9-]", "", topic.lower().replace(" ", "-")) or "general"
    path = os.path.join(MEMDIR, topic + ".md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new: f.write("# " + topic + "\n")
        f.write("- " + fact + "\n")
    return topic

EXAMPLE_FACTS = {"the user's boss fight feels too hard", "the user has a math test on friday", "the user likes dark themes"}

def remember(msg):
    try:
        note = ollama.chat(model=MEM_MODEL, think=False, keep_alive="30m", messages=[{"role": "user", "content":
            f"User said: '{msg}'. If it contains a lasting fact about the user, their projects, games or preferences, reply as: topic | one short sentence. The topic is one or two lowercase words like about-me, projects, school. Otherwise reply NONE. Reply with only the answer, not the arrow or the user's words. Use projects for anything about the user's own projects or games. Examples: 'my boss fight is too hard' -> projects | The user's boss fight feels too hard. 'I have a math test friday' -> school | The user has a math test on Friday. 'I like dark themes' -> about-me | The user likes dark themes. 'how do I make a loop' -> NONE. 'thanks' -> NONE. /no_think"}])["message"]["content"].split("</think>")[-1].strip()
    except Exception:
        return
    if "->" in note: note = note.split("->")[-1].strip()
    if "NONE" not in note and "|" in note:
        topic, fact = note.split("|", 1)
        if topic.strip().lower() not in ("about-me", "projects", "school"):
            topic = "general"
        f0 = fact.strip().rstrip(".").lower()
        if f0 in EXAMPLE_FACTS or f0 in load_mem().lower(): return
        t = save_mem(topic.strip(), fact.strip())
        console.print(f"[green]●[/] [bold]Remember[/]([cyan]{t}.md[/])\n  [dim]⎿  {fact.strip()}[/]")

BANNER = r"""
 ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
 ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
 █████╗  ██║   ██║██████╔╝██║  ███╗█████╗
 ██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
 ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
 ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝"""


PET = {
 "idle": ['        [#ffd166]▗▖[/]      ', '       [#ff8c42]▟[#ffd166]██[/]▙[/]     ', '      [#e8590c]▐[#ff8c42]█[#ffd166]▀▀[/]█[/]▌[/]    ', ' [#9aa0a6]▄▄▄▄▄▄▄▄▄▄▄▄▄[/] ', ' [#9aa0a6]▀▀▜██[/][white]▐▌[/][#9aa0a6]███[/][white]▐▌[/][#9aa0a6]██▛[/] ', '     [#6b7280]▐█████▌[/]    ', '    [#6b7280]▟███████▙[/]   '],
 "think": ['      [#ffd166]▖ ▟▖ ▗[/]    ', '      [#ff8c42]▗█[#ffd166]██[/]█▖[/]    ', '      [#e8590c]▐[#ff8c42]█[#ffd166]██[/]█[/]▌[/]    ', ' [#9aa0a6]▄▄▄▄▄▄▄▄▄▄▄▄▄[/] ', ' [#9aa0a6]▀▀▜██[/][white]▀▀[/][#9aa0a6]███[/][white]▀▀[/][#9aa0a6]██▛[/] ', '     [#6b7280]▐█████▌[/]    ', '    [#6b7280]▟███████▙[/]   '],
 "happy": ['     [#ffd166]▝ [/][#ffd166]▗▖[/][#ffd166] ▘[/]    ', '       [#ff8c42]▟[#ffd166]██[/]▙[/]     ', '      [#e8590c]▐[#ff8c42]█[#ffd166]▄▄[/]█[/]▌[/]    ', ' [#9aa0a6]▄▄▄▄▄▄▄▄▄▄▄▄▄[/] ', ' [#9aa0a6]▀▀▜██[/][white]▄▄[/][#9aa0a6]███[/][white]▄▄[/][#9aa0a6]██▛[/] ', '     [#6b7280]▐█████▌[/]    ', '    [#6b7280]▟███████▙[/]   '],
}
def pet(mood, say=""):
    lines = PET[mood][:]
    if say: lines[3] += "  [italic #ffd166]" + say + "[/]"
    return "\n".join(lines)

def read_file(path):
    text = open(path, encoding="utf-8", errors="replace").read()[:6000]
    console.print(f"[green]●[/] [bold]Read[/]([cyan]{path}[/])\n  [dim]⎿  Read {text.count(chr(10))+1} lines[/]")
    return text


def yes(ans): return ans.strip().lower() in ("y","yes","j","ja")
def ask_yn(q, allow_all=False):
    """Returns 'y', 'n' or 'a' (yes to all). Tests replace this function."""
    extra = "/a=yes to all" if allow_all else ""
    a = session.prompt(HTML(f"<ansiyellow>{q} (y/n{extra}) </ansiyellow>")).strip().lower()
    if allow_all and a in ("a", "all"): return "a"
    return "y" if yes(a) else "n"

def tool_line(name, arg, note="", color="green"):
    console.print(f"[{color}]●[/] [bold]{name}[/]([cyan]{arg}[/])" + (f"\n  [dim]⎿  {note}[/]" if note else ""), highlight=False)

SHELL_NAME = "PowerShell" if IS_WIN else "Bash"
# ---------- 4. shell commands ----------
def run_cmd(cmd, auto=False, header=True):
    """Show ● Bash(cmd), ask y/n, run it. Returns output text, or None if the user said no."""
    from rich.markup import escape
    if header: console.print(f"[green]●[/] [bold]{SHELL_NAME}[/]([cyan]{escape(cmd)}[/])", highlight=False)
    if not auto and ask_yn("⚡ Run this command?") != "y":
        console.print("[dim]  ⎿  Skipped, nothing was run.[/]"); return None
    try:
        if IS_WIN:
            p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], cwd=os.getcwd(), capture_output=True,
                               text=True, timeout=60, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            p = subprocess.run(cmd, shell=True, cwd=os.getcwd(), capture_output=True, text=True, timeout=60, errors="replace")
        out = (p.stdout + p.stderr).rstrip() + ("" if p.returncode == 0 else f"\n(exit code {p.returncode})")
    except subprocess.TimeoutExpired:
        out = "(stopped: took longer than 60 seconds)"
    except Exception as e:
        out = f"(could not run: {e})"
    lines = out.splitlines() or ["(no output)"]
    shown = lines[:40]
    for i, l in enumerate(shown):
        console.print(Text(("  ⎿  " if i == 0 else "     ") + l[:200], style="dim"))
    if len(lines) > 40: console.print(Text(f"     … {len(lines)-40} more lines", style="dim"))
    return out[:4000]

def extract_commands(reply):
    """Find commands the model proposed: ```bash blocks or RUN: lines."""
    cmds = []
    for block in re.findall(r"```(?:bash|sh|shell|console|powershell|pwsh|ps1|ps|cmd|bat)\s*\n(.*?)```", reply, re.S):
        for l in block.splitlines():
            l = l.strip()
            if l.startswith("$ "): l = l[2:]
            if l.startswith("PS> "): l = l[4:]
            if l and not l.startswith("#"): cmds.append(l)
    for m in re.findall(r"(?m)^\s*\**RUN:\**\s*`?(.+?)`?\s*$", reply):
        cmds.append(m.strip())
    seen = []
    for c in cmds:
        if c not in seen: seen.append(c)
    return seen[:3]

# ---------- 6. project search ----------
SKIP_DIRS = {".git", "node_modules", "Library", "Temp", "venv", ".venv", "env", "ai-env", "__pycache__", "obj", "Build", "Builds", "Logs", ".cache", ".local", "site-packages", ".npm", "snap"}
BIN_EXT = {".png",".jpg",".jpeg",".gif",".zip",".gz",".tar",".so",".dll",".exe",".bin",".pdf",".mp3",".mp4",".wav",".ogg",".fbx",".blend",".pyc",".asset",".meta",".gguf",".ttf",".psd",".unity3d",".bundle",".db",".sqlite",".iso",".deb"}
STOP = set("the a an and or to of in on for is it my me this that what how why where with can you your does do from file files code project about show find search where which there are was be have has please make add fix".split())

def keywords(text):
    ws = [w for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text) if w.lower() not in STOP]
    out = []
    for w in ws:
        if w.lower() not in [o.lower() for o in out]: out.append(w)
    return out[:6]

def candidate_files(root, kws):
    if shutil.which("rg"):
        try:
            args = ["rg", "-l", "-i", "--max-filesize", "300K"] + sum([["-g", "!" + d] for d in SKIP_DIRS], [])
            for k in kws: args += ["-e", re.escape(k)]
            r = subprocess.run(args + [root], capture_output=True, text=True, timeout=15)
            return [l for l in r.stdout.splitlines() if l][:400]
        except Exception: pass
    files, start = [], time.time()
    for d, dirs, fs in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".") and "venv" not in x]
        for f in fs:
            if os.path.splitext(f)[1].lower() in BIN_EXT: continue
            files.append(os.path.join(d, f))
        if len(files) > 4000 or time.time() - start > 4: break
    return files

def project_search(query, root=None, show=True):
    """Returns (summary_text_for_model, list_of_paths)."""
    root = root or os.getcwd()
    kws = keywords(query)
    if not kws: return "", []
    results = []
    for path in candidate_files(root, kws):
        try:
            if os.path.getsize(path) > 300_000: continue
            with open(path, "rb") as fh: raw = fh.read()
            if b"\0" in raw[:2000]: continue
            text = raw.decode("utf-8", "replace")
        except Exception: continue
        low = text.lower(); name = os.path.basename(path).lower()
        score = sum(min(low.count(k.lower()), 20) for k in kws) + sum(10 for k in kws if k.lower() in name)
        hits = len([k for k in kws if k.lower() in low or k.lower() in name])
        if score: results.append((hits, score, path, text))
    results.sort(key=lambda r: (-r[0], -r[1]))
    if show: tool_line("Search", '"' + " ".join(kws) + '"', f"Found {len(results)} file{'s' if len(results)!=1 else ''}")
    note = ""
    for hits, score, path, text in results[:4]:
        try: rel = os.path.relpath(path, root)
        except ValueError: rel = path
        snips = [f"{i+1}: {l.strip()[:160]}" for i, l in enumerate(text.splitlines()) if any(k.lower() in l.lower() for k in kws)][:6]
        if show: console.print(Text(f"     {rel}", style="dim"))
        note += f"\n--- {rel} ---\n" + "\n".join(snips)
    return note, [r[2] for r in results[:4]]

# ---------- 9. web search ----------
WEB_WORDS = ("latest", "news", "today", "price", "2025", "2026", "search the web", "search online", "google", "look up", "current", "weather", "newest", "release date")
def wants_web(msg):
    m = msg.lower()
    return any(w in m for w in WEB_WORDS) or m.startswith("search ")

def web_search(q, n=5, show=True):
    """Returns list of {title,url,snippet}. Never raises."""
    res, err = [], ""
    try:
        try: from ddgs import DDGS
        except ImportError: from duckduckgo_search import DDGS
        for r in DDGS().text(q, max_results=n) or []:
            res.append({"title": r.get("title",""), "url": r.get("href") or r.get("url",""), "snippet": r.get("body","")})
    except Exception as e:
        err = str(e)
    if not res:
        try:
            req = urllib.request.Request("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q), headers={"User-Agent": "Mozilla/5.0"})
            page = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
            links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)
            snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S)
            for i, (u, t) in enumerate(links[:n]):
                if "uddg=" in u: u = urllib.parse.unquote(u.split("uddg=")[1].split("&")[0])
                clean = lambda s: htmlmod.unescape(re.sub(r"<.*?>", "", s)).strip()
                res.append({"title": clean(t), "url": u, "snippet": clean(snips[i]) if i < len(snips) else ""})
        except Exception as e:
            err = err or str(e)
    if show:
        tool_line("WebSearch", '"' + q + '"', f"{len(res)} results" if res else "No results (am I offline? 📡)", "green" if res else "red")
        for r in res[:n]: console.print(Text(f"     {r['title'][:70]} — {r['url'][:80]}", style="dim"))
    return res

def web_note(res):
    if not res: return "\n\n(Web search found nothing or the internet is offline. Tell the user you couldn't search the web; don't invent current facts.)"
    return "\n\nWeb search results (cite the links you use as [title](url)):\n" + "\n".join(f"{i+1}. {r['title']} — {r['url']}\n   {r['snippet'][:300]}" for i, r in enumerate(res))

# ---------- 7. to-do list ----------
TODO = []
def show_todo():
    if not TODO: console.print("[dim]  ⎿  No to-do list yet. Try /plan <task>[/]"); return
    console.print("[green]●[/] [bold]Update Todos[/]")
    for i, t in enumerate(TODO):
        pre = "  ⎿  " if i == 0 else "     "
        console.print(Text(pre + ("☒ " if t["done"] else "☐ ") + t["text"], style="dim strike" if t["done"] else "white"))

def parse_plan(text):
    steps = []
    for l in text.split("</think>")[-1].splitlines():
        m = re.match(r"\s*(?:\d+[.)]|[-*•]|\[ ?\]|☐)\s+(.+)", l)
        if m: steps.append(m.group(1).strip().strip("*").strip())
    return [(s if len(s) <= 80 else s[:80].rsplit(" ", 1)[0] + "…") for s in steps if s][:8]

def make_plan(task):
    global TODO
    with console.status("[#ff8c42]✻ Planning…[/]"):
        out = ollama.chat(model=PLAN_MODEL, think=False, keep_alive="30m", options={"num_predict": 300}, messages=[{"role": "user", "content":
            "Make a short checklist (3 to 6 steps) to do this task: " + task + "\nReply ONLY with a numbered list, one short step (under 10 words) per line. /no_think"}])["message"]["content"]
    steps = parse_plan(out) or [task[:90]]
    TODO = [{"text": s, "done": False} for s in steps]
    show_todo()

def check_next():
    for t in TODO:
        if not t["done"]: t["done"] = True; return

# ---------- 5. edits (many files + new files) ----------
EDIT_WORDS = ("edit","change","fix","add","remove","rename","replace","update","make","delete","refactor","create","write")
FILE_RE = re.compile(r"[\w./~-]+\.[A-Za-z0-9]{1,5}\b")
def wants_edit(msg):
    return msg.lower().split()[0] in EDIT_WORDS if msg.split() else False

def parse_edits(out, default=None):
    """Returns (edits {path:[(search,replace)]}, new_files {path:content})."""
    edits, new = {}, {}
    parts = re.split(r"(?m)^[ \t*#]*(NEW FILE|FILE):\s*`?([^\s`*]+)`?\**[ \t]*$", out)
    pieces = [(None, default, parts[0])] + [(parts[i], parts[i+1], parts[i+2]) for i in range(1, len(parts) - 2, 3)]
    for kind, name, body in pieces:
        if kind == "NEW FILE":
            m = re.search(r"```[^\n]*\n(.*?)\n?```", body, re.S)
            content = m.group(1) if m else body.strip("\n")
            if content.strip(): new[name] = content.rstrip("\n") + "\n"
            continue
        blocks = re.findall(r"<<<<<<< SEARCH\n(.*?)\n=======\n(.*?)\n?>>>>>>> REPLACE", body, re.S)
        if blocks and name: edits.setdefault(name, []).extend(blocks)
    return edits, new

def resolve(p, known):
    for k in known:
        if os.path.abspath(os.path.expanduser(p)) == os.path.abspath(k) or os.path.basename(k) == p: return k
    return os.path.abspath(os.path.expanduser(p))

def apply_changes(changes, auto=False):
    """changes: {path: (old_text_or_None, new_text)}. Shows diffs, asks, backs up, writes, records undo. Returns list of written paths."""
    import difflib, py_compile
    from rich.syntax import Syntax
    for path, (old, new) in changes.items():
        if old is None:
            console.print(Panel(Syntax(new[:3000], "python" if path.endswith(".py") else "text", theme="monokai"), title=f"New file: {path}", border_style="#ff8c42"))
        else:
            diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), path, path))
            console.print(Panel(Syntax(diff, "diff", theme="monokai"), title=f"Proposed change: {path}", border_style="#ff8c42"))
    chosen = list(changes)
    if not auto:
        if len(changes) > 1:
            a = session.prompt(HTML(f"<b>Apply all {len(changes)} changes? (y=all / n=none / e=ask for each) </b>")).strip().lower()
            if a.startswith("e"): chosen = [p for p in changes if ask_yn(f"Apply change to {p}?") == "y"]
            elif not yes(a): chosen = []
        elif ask_yn("Apply this change?") != "y": chosen = []
    if not chosen:
        console.print("[dim]  ⎿  Skipped, nothing changed.[/]"); return []
    bdir = BACKUP_DIR; os.makedirs(bdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S"); record = []
    for path in chosen:
        old, new = changes[path]
        bak = None
        if old is not None:
            bak = os.path.join(bdir, datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + "_" + os.path.basename(path))
            open(bak, "w", encoding="utf-8", newline="").write(old)
            same = sorted(glob.glob(os.path.join(bdir, "*_" + os.path.basename(path))))
            for extra in same[:-10]: os.remove(extra)
        else:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        open(path, "w", encoding="utf-8", newline="").write(new); record.append({"path": path, "bak": bak})
        console.print(f"[green]●[/] {'Created' if bak is None else 'Saved'} [cyan]{path}[/]" + (f" · backup [cyan]{bak}[/]" if bak else "") + " 🔥")
        if path.endswith(".py"):
            try: py_compile.compile(path, doraise=True); console.print("[dim]  ⎿  Still runs (compiles fine) ✅[/]")
            except Exception as e:
                if os.path.abspath(path) == os.path.abspath(__file__) and bak:
                    open(path, "w", encoding="utf-8", newline="").write(old); console.print(f"[red]●[/] That change to my own code broke me ({e}), so I put my old code back. 🛡️"); continue
                console.print(f"[red]●[/] Warning: it doesn't compile now: {e}. /undo can revert it.")
        if os.path.abspath(path) == os.path.abspath(__file__):
            console.print("[#ffd166]  ⎿  I upgraded myself! Type /bye and start forge again to load it. 🔥[/]")
    json.dump({"files": record}, open(LAST_EDIT, "w", encoding="utf-8"))
    return chosen

def relevant_parts(text, msg, limit=10000):
    parts = re.split(r"(?m)^(?=def |class |[A-Z_]+ = )", text)
    stop = {"the","and","for","you","your","yourself","change","add","make","can","that","this","with","fix","code","own","say","says"}
    words = {w for w in re.findall(r"[a-z_]{3,}", msg.lower())} - stop
    scored = sorted(range(len(parts)), key=lambda i: -sum(w in parts[i].lower() for w in words))
    keep, size = set(), 0
    for i in scored:
        if size + len(parts[i]) > limit: continue
        keep.add(i); size += len(parts[i])
    return "\n# ...\n".join(parts[i] for i in sorted(keep))

def do_edit(paths, msg, auto=False):
    """Edit existing files in paths and/or create new ones. Returns a short summary string."""
    if isinstance(paths, str): paths = [paths]
    files = {}
    for p in paths:
        t = open(p, encoding="utf-8", errors="replace").read()
        if len(t) > 12000:
            t = relevant_parts(t, msg)
            console.print(f"[dim]  ⎿  {os.path.basename(p)} is big, so I'm only looking at the parts that match your request[/]")
        files[p] = t
    tool_line("Edit", ", ".join(paths) or "new file", f"using {EDIT_MODEL} (careful mode, slower)")
    prompt = "You edit code. Request: " + msg + "\n\n" + "".join(f"File {p}:\n```\n{t}\n```\n\n" for p, t in files.items()) + (
        "Reply ONLY with blocks in exactly this format. To change an existing file:\nFILE: path/to/file\n<<<<<<< SEARCH\nexact old lines copied from the file\n=======\nnew lines\n>>>>>>> REPLACE\n"
        "To create a NEW file:\nNEW FILE: path/to/newfile\n```\nwhole file content\n```\nNo other text. /no_think")
    with console.status("[#ff8c42]✻ Forging the edit…[/]"):
        out = ollama.chat(model=EDIT_MODEL, think=False, keep_alive="30m", options={"num_predict": 2000, "num_ctx": 8192},
                          messages=[{"role": "user", "content": prompt}])["message"]["content"].split("</think>")[-1]
    return apply_model_edit(out, paths, auto)

def apply_model_edit(out, paths, auto=False):
    edits, new = parse_edits(out, paths[0] if len(paths) == 1 else None)
    changes = {}
    for p, blocks in edits.items():
        real = resolve(p, paths)
        if not os.path.isfile(real):
            console.print(f"[red]●[/] I tried to edit {p} but it doesn't exist, skipping it."); continue
        old = open(real, encoding="utf-8", errors="replace").read(); txt = old
        for s, r in blocks:
            if txt.count(s) != 1:
                console.print(f"[red]●[/] My edit for {p} didn't match the file exactly, so I changed nothing there."); txt = None; break
            txt = txt.replace(s, r, 1)
        if txt is not None and txt != old: changes[real] = (old, txt)
    for p, content in new.items():
        real = resolve(p, paths)
        if os.path.exists(real):
            console.print(f"[red]●[/] {p} already exists, so I won't overwrite it as a new file."); continue
        changes[real] = (None, content)
    if not changes:
        console.print("[red]●[/] I couldn't come up with a clean edit. Try saying it more exactly. 🤔"); return "no edit made"
    done = apply_changes(changes, auto)
    return ("changed: " + ", ".join(done)) if done else "the user said no, nothing changed"

# ---------- 8. agent loop ----------
AGENT_PROMPT = """You are Forge working by yourself on a task for the user in the folder {cwd}.
Task: {task}
To-do list:
{todo}
Each turn reply with EXACTLY two lines and nothing else:
THOUGHT: <one short sentence>
ACTION: <one of these>
  read <file path>
  search <keywords>
  edit <file path> <what to change, or what the new file should contain>
  run <one shell command>
  done <short summary for the user>
Use only one action per reply. Never claim something worked unless the RESULT says so. /no_think"""

def parse_action(text):
    """Returns (verb, arg) or (None, None)."""
    text = text.split("</think>")[-1]
    m = re.search(r"(?im)^\s*\**ACTION:?\**\s*:?\s*(read|search|edit|run|done)\b[:\s]*(.*)$", text)
    if not m: m = re.search(r"(?im)^\s*(read|search|edit|run|done)\b[:\s]+(.*)$", text)
    if not m: return None, None
    return m.group(1).lower(), m.group(2).strip().strip("`").strip()

def agent(task, max_steps=8):
    global TODO
    console.print(f"[green]●[/] [bold]Agent[/]([cyan]{task[:60]}[/])\n  [dim]⎿  up to {max_steps} steps · I'll ask before every change or command · Ctrl+C to stop[/]")
    if not TODO or all(t["done"] for t in TODO): make_plan(task)
    auto = False; errors = 0; msgs = []; summary = "stopped"
    try:
        for step in range(1, max_steps + 1):
            todo_txt = "\n".join(("[x] " if t["done"] else "[ ] ") + t["text"] for t in TODO)
            sys_p = AGENT_PROMPT.format(cwd=os.getcwd(), task=task, todo=todo_txt)
            with console.status(f"[#ff8c42]✻ Step {step}/{max_steps}: thinking…[/]"):
                out = ollama.chat(model=SMART_MODEL, think=False, keep_alive="30m", options={"num_predict": 300},
                                  messages=[{"role": "system", "content": sys_p}] + msgs[-10:] + [{"role": "user", "content": "What is your next action?"}])["message"]["content"].split("</think>")[-1].strip()
            verb, arg = parse_action(out)
            th = re.search(r"(?im)^\s*THOUGHT:\s*(.+)$", out)
            if th: console.print(Text("✻ " + th.group(1).strip()[:150], style="italic #ffd166"))
            msgs.append({"role": "assistant", "content": out})
            if not verb or (verb != "done" and not arg):
                errors += 1; result = "I could not understand that. Reply with THOUGHT: and ACTION: lines only."
                console.print("[red]●[/] [dim]Couldn't read my own plan, retrying…[/]")
                if errors >= 3: console.print("[red]●[/] Too many confused steps, stopping. 😅"); break
                msgs.append({"role": "user", "content": "RESULT: " + result}); continue
            if verb == "done":
                for t in TODO: t["done"] = True
                summary = arg or "Finished!"; show_todo()
                console.print(Group(Text.from_markup(pet("happy", "done!")), Text("● Forge", style="bold white"), Markdown(summary))); break
            if verb == "read":
                p = os.path.expanduser(arg.split()[0])
                result = read_file(p)[:4000] if os.path.isfile(p) else f"No file named {p}."
            elif verb == "search":
                result = project_search(arg)[0] or "No matching files."
            elif verb == "run":
                if not auto:
                    from rich.markup import escape
                    console.print(f"[green]●[/] [bold]{SHELL_NAME}[/]([cyan]{escape(arg)}[/])", highlight=False)
                    a = ask_yn("⚡ Run this command?", allow_all=True)
                    if a == "a": auto = True
                    if a == "n": result = "the user said no to running this command."; console.print("[dim]  ⎿  Skipped.[/]")
                    else: result = run_cmd(arg, auto=True, header=False)
                else: result = run_cmd(arg, auto=True)
                if result and "said no" not in result: check_next()
            elif verb == "edit":
                parts = arg.split(None, 1)
                p = os.path.expanduser(parts[0]); instr = parts[1] if len(parts) > 1 else task
                if not auto:
                    a = ask_yn(f"✏️  Let me edit {p}? (you'll still see the diff)", allow_all=True)
                    if a == "a": auto = True
                    if a == "n": msgs.append({"role": "user", "content": "RESULT: the user said no to editing."}); continue
                if os.path.isfile(p): result = do_edit([p], instr, auto=auto)
                else: result = do_edit([], f"Create the new file {p}: {instr}", auto=auto)
                if result.startswith("changed"): check_next(); show_todo()
                else: errors += 1
            if errors >= 3: console.print("[red]●[/] Too many problems, stopping here. 😅"); break
            msgs.append({"role": "user", "content": "RESULT:\n" + str(result)[:3000]})
        else:
            console.print("[dim]  ⎿  Reached the step limit. Say /agent again to keep going.[/]")
    except KeyboardInterrupt:
        console.print("[dim]  ⎿  Agent stopped ✋[/]")
    return summary

BIG_WORDS = ("build", "create a", "make a", "make me", "set up", "setup", "implement", "step by step", "multiple", "refactor", "whole", "project")
def big_task(msg):
    m = msg.lower()
    return len(msg.split()) >= 8 and any(w in m for w in BIG_WORDS)

CHAT_FILE = str(FORGE_DIR / "memory" / ".last-chat.json")
LAST_EDIT = str(FORGE_DIR / "backups" / ".last-edit.json")
HELP = """[bold #ff8c42]Forge commands[/]
  [cyan]/help[/]           show this list
  [cyan]/clear[/]          start a fresh chat
  [cyan]/model[/]          models per role + installed models
  [cyan]/model chat|code|plan <name>[/]  change a role (saved)
  [cyan]/model suggest[/]  recommend models for this PC's RAM/GPU
  [cyan]/undo[/]           undo my last edit (all files; deletes files I created)
  [cyan]/deep[/] <q>       think step by step (or say y when I ask)
  [cyan]/run[/] <cmd>      run a shell command (I always ask y/n first) ⚡
  [cyan]/search[/] <words> search the files in this folder 🔍
  [cyan]/web[/] <query>    search the internet 🌐
  [cyan]/plan[/] <task>    make a to-do list ☐
  [cyan]/todo[/]           show the to-do list
  [cyan]/agent[/] <task>   I work on it by myself, step by step (asks before changes; a = yes to all) 🤖
  [cyan]/read[/] <file>    read and summarize a file
  [cyan]/bye[/]            quit (your chat is saved)
  [cyan]Ctrl+C[/]          stop me mid-answer
  Mention a file to read it · start with fix/change/add/create + file name(s) to edit or create files
  Ask about code without a file and I'll search this folder · say latest/news/today/price to search the web"""
def save_chat(h):
    if h: json.dump(h[-20:], open(CHAT_FILE, "w", encoding="utf-8"))
def undo():
    if not os.path.exists(LAST_EDIT):
        console.print("[dim]  ⎿  Nothing to undo.[/]"); return
    e = json.load(open(LAST_EDIT, encoding="utf-8"))
    for f in e.get("files", [e]):
        if f.get("bak"):
            open(f["path"], "w", encoding="utf-8", newline="").write(open(f["bak"], encoding="utf-8").read())
            tool_line("Undo", f["path"], f"Restored from {f['bak']} ↩️")
        elif os.path.exists(f["path"]):
            os.remove(f["path"]); tool_line("Undo", f["path"], "Deleted the file I created ↩️")
    os.remove(LAST_EDIT)

# ---------- /model ----------
def installed_models():
    try:
        r = ollama.list()
        ms = r.get("models", []) if isinstance(r, dict) else getattr(r, "models", [])
        return sorted((m.get("model") or m.get("name")) if isinstance(m, dict) else (getattr(m, "model", None) or getattr(m, "name", "")) for m in ms)
    except Exception: return []

def _norm(n): return n if ":" in n else n + ":latest"

def detect_hardware():
    """Returns dict(ram_gb, gpu, vram_gb). Works on Windows, Linux and macOS; never raises."""
    ram = 0.0
    try:
        if IS_WIN:
            import ctypes
            class MS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("avail", ctypes.c_ulonglong),
                            ("tp", ctypes.c_ulonglong), ("ap", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("ae", ctypes.c_ulonglong)]
            m = MS(); m.l = ctypes.sizeof(MS); ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)); ram = m.total / 2**30
        elif sys.platform == "darwin":
            ram = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5).stdout) / 2**30
        else:
            ram = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30
    except Exception: pass
    gpu, vram = None, 0.0
    smi = shutil.which("nvidia-smi") or (r"C:\Windows\System32\nvidia-smi.exe" if IS_WIN and os.path.exists(r"C:\Windows\System32\nvidia-smi.exe") else None)
    if smi:
        try:
            out = subprocess.run([smi, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
            if out:
                name, mem = out[0].rsplit(",", 1); gpu, vram = name.strip(), float(mem) / 1024
        except Exception: pass
    if not gpu and sys.platform == "darwin" and platform.machine() == "arm64":
        gpu, vram = "Apple Silicon (unified memory)", ram * 0.65
    return {"ram_gb": round(ram, 1), "gpu": gpu, "vram_gb": round(vram, 1)}

def suggest_models(hw):
    v, ram = hw["vram_gb"], hw["ram_gb"]
    if v >= 16: return {"chat": "qwen3:4b", "code": "qwen3:14b", "plan": "qwen3:14b"}
    if v >= 12: return {"chat": "qwen3:4b", "code": "qwen3:8b", "plan": "qwen3:8b"}
    if v >= 8: return {"chat": "qwen3:4b", "code": "qwen3:8b", "plan": "qwen3:4b"}
    if v >= 4: return {"chat": "qwen3:1.7b", "code": "qwen3:4b", "plan": "qwen3:4b"}
    if ram >= 16: return {"chat": "qwen3:1.7b", "code": "qwen3:4b", "plan": "qwen3:1.7b"}  # CPU only
    return {"chat": "qwen3:1.7b", "code": "qwen3:1.7b", "plan": "qwen3:1.7b"}

ROLE_DESC = {"chat": "chat, reasoning, memory notes", "code": "code, files, explaining, edits, deep thinking, agent", "plan": "to-do lists and plans"}
def model_cmd(arg):
    global CHAT_MODEL, SMART_MODEL, EDIT_MODEL, PLAN_MODEL, MEM_MODEL
    parts = arg.split()
    inst = installed_models(); inst_n = {_norm(m) for m in inst}
    cur = {"chat": CHAT_MODEL, "code": SMART_MODEL, "plan": PLAN_MODEL}
    if not parts:
        console.print("[bold #ff8c42]Models per role[/]")
        for r, m in cur.items():
            ok = "" if _norm(m) in inst_n else " [red](not installed: ollama pull " + m + ")[/]"
            console.print(f"  [cyan]{r:5}[/] {m}{ok}  [dim]{ROLE_DESC[r]}[/]")
        console.print("[bold #ff8c42]Installed[/]  " + (", ".join(inst) if inst else "[red]none found (is Ollama running?)[/]"))
        console.print("[dim]  ⎿  /model chat|code|plan <name> to change · /model suggest for this computer[/]"); return
    if parts[0] == "suggest":
        hw = detect_hardware(); sug = suggest_models(hw)
        g = f"{hw['gpu']} ({hw['vram_gb']} GB VRAM)" if hw["gpu"] else "no NVIDIA GPU found, CPU only"
        console.print(f"[bold #ff8c42]Your computer[/]  RAM {hw['ram_gb']} GB · GPU {g}")
        pulls = []
        for r, m in sug.items():
            have = _norm(m) in inst_n
            if not have and m not in pulls: pulls.append(m)
            console.print(f"  [cyan]{r:5}[/] {m}  " + ("[green]installed ✅[/]" if have else "[yellow]not installed[/]") + f"  [dim]{ROLE_DESC[r]}[/]")
        if pulls: console.print("[dim]  ⎿  Get them with:[/] " + " ; ".join("ollama pull " + m for m in pulls))
        console.print("[dim]  ⎿  Then set them with e.g. /model code " + sug["code"] + "[/]"); return
    if parts[0] in ("chat", "code", "plan", "think") and len(parts) == 2:
        role = "plan" if parts[0] == "think" else parts[0]; name = parts[1]
        if inst and _norm(name) not in inst_n:
            console.print(f"[yellow]●[/] {name} isn't installed yet. Run: ollama pull {name}  (saved anyway)")
        if role == "chat": CHAT_MODEL = MEM_MODEL = name
        elif role == "code": SMART_MODEL = EDIT_MODEL = name
        else: PLAN_MODEL = name
        models = load_config().get("models", {}); models[role] = name; save_config(models=models)
        console.print(f"[green]●[/] {role} model is now [cyan]{name}[/] [dim](saved in {CONFIG_FILE})[/]"); return
    console.print("[dim]  ⎿  Usage: /model · /model chat|code|plan <name> · /model suggest[/]")

def stream_reply(model, messages, deep=False, n=2000):
    raw = ""; tokens = 0; start = time.time()
    try:
        with Live(console=console, refresh_per_second=8, transient=False) as live:
            for chunk in ollama.chat(model=model, messages=messages, stream=True, think=deep, keep_alive="30m", options={"num_predict": 2000 if deep else n}):
                raw += chunk["message"].get("content", "") or ""
                tokens += 1
                visible = raw.split("</think>")[-1].strip() if "</think>" in raw else ("" if "<think>" in raw else raw)
                status = Text(f"{SPIN[tokens % len(SPIN)]} Forging… ({int(time.time()-start)}s · ⚒ {tokens} tokens)", style="#ff8c42")
                if visible: live.update(Group(Text("● ", style="white", end=""), Markdown(visible), status))
                else: live.update(Group(Text.from_markup(pet("think", "hmm...")), status))
            reply = raw.split("</think>")[-1].strip()
            live.update(Group(Text.from_markup(pet("happy", "done!")), Text("● Forge", style="bold white"), Markdown(reply),
                              Text(f"  ⎿ {tokens} tokens in {time.time()-start:.1f}s", style="dim")))
    except KeyboardInterrupt:
        reply = raw.split("</think>")[-1].strip() + " [stopped]"
        console.print("[dim]  ⎿  Stopped ✋[/]")
    return reply

SPIN = "✻✶✷✸✹✺"
session = None

FEATURES = """Everything Forge can do (keep this list up to date):
- Chat with model routing by role: a chat model (normal chat, reasoning, memory notes), a code model (code, files, explaining, edits, deep thinking, agent) and a plan model (to-do lists). Offers deeper thinking with y/n on tricky questions (/deep).
- Memory notes about the user saved automatically in ~/Forge/memory.
- Saved chats: every chat is saved; on start Forge asks 'Continue our last chat?' and, on y, shows the previous messages and continues. /clear or 'start over' starts fresh.
- Reads files the user mentions; searches the project for code questions (/search); web search with links (/web, or automatic for latest/news/today/price).
- Runs shell commands after y/n (/run, or suggests RUN: lines).
- Data lives in ~/Forge (memory/, backups/, tests/; on Windows C:\\Users\\<you>\\Forge). Backups are named date_time_filename and only the newest 10 per file are kept.
- Edits and creates one or more files with a preview and y/n, backups in ~/Forge/backups, /undo or 'undo that' reverts the last edit.
- To-do lists (/plan, /todo, or offered automatically for multi-step tasks); agent mode (/agent) works step by step on its own with y/n/a approvals.
- Natural words work instead of commands ('undo that', 'start over', 'which model', 'show my todo', 'what can you do', 'bye forge'); typing / opens a command menu.
- /model shows the model used for each role (chat, code, plan) and the installed models; '/model chat <name>', '/model code <name>' and '/model plan <name>' change a role (saved in ~/.forge/config.json); '/model suggest' detects RAM, GPU and VRAM (nvidia-smi, Apple Silicon, or CPU only) and recommends models that fit, says which are installed and gives the 'ollama pull' command for the rest.
- Works on Windows 10/11 (PowerShell / Windows Terminal, colors and emoji, `forge` command via install.ps1), Linux and macOS. On Windows /run and suggested commands run in PowerShell; on Linux/macOS in bash.
- Starts Ollama by itself if it isn't running (hidden background process on Windows). Ctrl+C stops an answer. Has a pet: Forge the anvil with a flame.
- Typing predictions: grey ghost text finishes what the user types based on what they typed before; → accepts it, ↑ shows older messages.
- Can upgrade himself: when the user says e.g. 'add X to yourself', Forge edits his own forge.py with a preview and y/n, backs up first, and auto-restores if the change breaks him; then the user restarts forge."""

def replay(h, n=10):
    console.print("[dim]── last chat ──────────────────────────────[/]")
    for m in h[-n:]:
        t = m["content"].split("\n\nContents of")[0].split("\n\nProject search results")[0].split("\n\nWeb search results")[0].strip()
        if len(t) > 500: t = t[:500] + " …"
        if m["role"] == "user": console.print(f"[bright_black]>[/] [bold]{t}[/]")
        else: console.print(Group(Text("● Forge", style="bold white"), Markdown(t)))
    console.print("[dim]── continuing ─────────────────────────────[/]")

def system_prompt():
    return ("You are Forge, " + USER_NAME + "'s personal AI assistant living on their computer. You help with anything: questions, school, " + ("Windows" if IS_WIN else platform.system()) + " and the computer, ideas, writing, coding and projects. Treat every topic as equally welcome and answer the question actually asked; only bring up the user's projects when they ask about them. You run fully offline through Ollama with model routing: " + CHAT_MODEL + " for normal chat, " + PLAN_MODEL + " for planning, reasoning and memory notes in ~/Forge/memory, and " + SMART_MODEL + " for code, reading files, explaining, edits and deep thinking. Be friendly and direct, explain simply like a teacher, show code in small pieces, use emojis now and then. Never make up facts or code; say you don't know instead. Today is " + datetime.date.today().isoformat() + ".\n"
        "The user's computer runs " + platform.system() + (": shell commands must be PowerShell" if IS_WIN else ": shell commands are bash") + ".\n"
        "Your tools (Forge's code runs them, you never run anything yourself):\n"
        "- Shell: if you need a command's output to answer (disk space, files in a folder, versions), reply with ONLY one line `RUN: <command>`. Forge shows it to the user, asks y/n, and gives you the output. Never pretend you ran a command or know its output before you get it.\n"
        "- Files: Forge reads files the user mentions and searches this folder for code questions; results appear in the user's message.\n"
        "- Edits: Forge edits or creates files when the user starts with fix/change/add/create and names files; you don't edit in chat.\n"
        "- Web: when the user's message contains web search results, use them and cite links as [title](url). Without results you have no internet info.\n"
        + FEATURES + "\nWhen the user asks what you can do or about a feature, answer from this list.\n"
        "Keep answers short. When explaining a file, only describe what is actually written in it and name the function or line. Your memory notes about the user (background only; use a note only when it is relevant to the current question, never steer the chat toward them):\n" + load_mem())

def main():
    global session, history
    console.print(Text(BANNER, style="bold #ff8c42"))
    console.print(pet("idle", "Hi " + USER_NAME + "! Forge here, let's build something. 🔥"))
    console.print(Panel(f"[bold]✻ Welcome to Forge![/]\n[dim]Models: {CHAT_MODEL} chat · {SMART_MODEL} code, explaining, edits & deep · /agent /run /web /search /plan · /help for commands[/]", border_style="#ff8c42", expand=False))
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    session = PromptSession(style=TB_STYLE, completer=CmdCompleter(), complete_while_typing=True,
                            history=FileHistory(str(FORGE_DIR / "memory" / ".typed-history")), auto_suggest=AutoSuggestFromHistory())
    history = []
    if os.path.exists(CHAT_FILE):
        try:
            old_chat = json.load(open(CHAT_FILE, encoding="utf-8"))
            if old_chat and yes(session.prompt(HTML(f"<ansiyellow>💬 Continue our last chat ({len(old_chat)//2} messages)? (y/n) </ansiyellow>"))):
                history = old_chat; replay(history)
        except Exception: pass
    with patch_stdout(raw=True):
        while True:
            console.print()
            try:
                msg = session.prompt(HTML("<ansibrightblack>╭──────────────────────────────────────────────╮\n│</ansibrightblack> <b>&gt;</b> "),
                    bottom_toolbar=HTML(" <ansimagenta>▸▸ Forge</ansimagenta> · local · <i>/bye to quit</i>"))
            except (EOFError, KeyboardInterrupt):
                break
            msg = msg.strip()
            if not msg: continue
            try:
                if not handle(msg): break
            except KeyboardInterrupt:
                console.print("[dim]  ⎿  Stopped ✋[/]")
            except Exception as e:
                console.print(f"[red]●[/] Something went wrong: {e}")
    save_chat(history)
    console.print(f"[#ff8c42]✻ Bye {USER_NAME}! 👋[/]")

NATURAL = [
    (("undo that","undo it","undo the last","revert that","take that back","undo my last"), "/undo"),
    (("start over","new chat","fresh chat","clear the chat","clear chat","forget this chat"), "/clear"),
    (("which model","what model","what models"), "/model"),
    (("show my todo","show the todo","my to-do","show to-do","what's on my list","whats on my list","todo list"), "/todo"),
    (("what can you do","what commands","show commands","help me use you"), "/help"),
    (("bye forge","goodbye","see you","i'm done","im done","quit forge","exit forge"), "/bye"),
]
PLAN_WORDS = ("steps to","step by step","plan for","plan out","make a plan","to-do","todo","how do i build","how do i make","how should i build","roadmap")
def natural_cmd(msg):
    m = msg.lower().strip(" ?!.")
    if len(m.split()) > 8: return None
    for phrases, c in NATURAL:
        if any(p in m for p in phrases): return c
    return None

history = []
def handle(msg):
    """Handle one message. Returns False to quit."""
    global history
    if not msg.startswith("/"):
        nc = natural_cmd(msg)
        if nc:
            console.print(f"[dim]  ⎿  (doing {nc})[/]"); msg = nc
    if not msg.startswith("/") and wants_edit(msg) and any(w in msg.lower() for w in ("yourself","your own code","your code","your file")):
        msg = msg + " (file: " + os.path.abspath(__file__) + ")"
    cmd, _, arg = msg.partition(" "); arg = arg.strip()
    if msg == "/bye": return False
    if msg == "/help": console.print(HELP); return True
    if msg == "/clear":
        history = []; console.print("[dim]  ⎿  Fresh chat started ✨[/]"); return True
    if cmd == "/model": model_cmd(arg); return True
    if msg == "/undo": undo(); return True
    if msg == "/todo": show_todo(); return True
    if cmd in ("/run", "/search", "/web", "/plan", "/agent") and not arg:
        console.print(f"[dim]  ⎿  Usage: {cmd} <{'command' if cmd=='/run' else 'words' if cmd!='/plan' and cmd!='/agent' else 'task'}>[/]"); return True
    console.print("[bright_black]╰──────────────────────────────────────────────╯[/]")
    if cmd == "/run":
        out = run_cmd(arg)
        if out is not None: history.append({"role": "user", "content": f"(the user ran `{arg}` himself. Output:)\n{out[:2000]}"}); history.append({"role": "assistant", "content": "Got it, I saw the output. 👍"}); save_chat(history)
        return True
    if cmd == "/plan": make_plan(arg); return True
    if cmd == "/agent": agent(arg); return True
    extra = ""; model = kind = None
    if cmd == "/search":
        note, _ = project_search(arg)
        msg = "Which files are about: " + arg + "? Explain briefly where things are."
        extra = "\n\nProject search results:" + (note or " nothing found.")
        model, kind = SMART_MODEL, "code"
    elif cmd == "/web":
        msg = arg; extra = web_note(web_search(arg)); model, kind = CHAT_MODEL, "web"
    if msg.startswith("/read "): msg = "Read and summarize " + msg[6:].strip()
    paths = []
    for w in msg.split():
        p = os.path.expanduser(w.strip("?,.!'\"`()"))
        if ("/" in w or "." in w) and os.path.isfile(p) and p not in paths: paths.append(p)
    if wants_edit(msg) and not cmd.startswith("/"):
        names = [os.path.expanduser(n) for n in FILE_RE.findall(msg)]
        if paths or names:
            try: do_edit(paths, msg)
            except Exception as e: console.print(f"[red]●[/] Edit failed: {e}")
            return True
    if not cmd.startswith("/") and big_task(msg) and yes(session.prompt(HTML("<ansiyellow>🛠️  This looks like a big task. Want me to work on it by myself, step by step? (y/n) </ansiyellow>"))):
        agent(msg); return True
    if not cmd.startswith("/") and any(w in msg.lower() for w in PLAN_WORDS) and yes(session.prompt(HTML("<ansiyellow>📋 Want me to make a to-do list for this? (y/n) </ansiyellow>"))):
        make_plan(msg); return True
    for p in paths:
        try: extra += "\n\nContents of " + p + ":\n```\n" + read_file(p) + "\n```"
        except Exception as e: console.print(f"[red]●[/] couldn't read {p}: {e}")
    if model is None:
        model, kind = route(msg, bool(extra))
        if not paths and kind == "code" and os.getcwd() != os.path.expanduser("~"):
            note, _ = project_search(msg)
            if note: extra += "\n\nProject search results (from the user's current folder):" + note
        if wants_web(msg):
            extra += web_note(web_search(re.sub(r"(?i)^search( the web| online)?( for)?\s*", "", msg)))
            if kind != "code": kind = "web"
    deep = msg.lower().startswith("/deep ")
    if deep: msg = msg[6:].strip()
    if not deep and kind == "reasoning" and len(msg.split()) >= 6:
        deep = yes(session.prompt(HTML("<ansiyellow>🤔 This looks like a tricky one. Think deeper? It's slower but smarter (y/n) </ansiyellow>")))
    if deep: model, kind = SMART_MODEL, "deep thinking"
    tool_line("Route", f"{model} · {kind}")
    history.append({"role": "user", "content": msg + extra})
    reply = stream_reply(model, [{"role": "system", "content": system_prompt()}] + history, deep)
    history.append({"role": "assistant", "content": reply}); save_chat(history)
    threading.Thread(target=remember, args=(msg,), daemon=True).start()
    # 4: commands the model proposed -> ask, run, feed back (max 2 rounds)
    for _ in range(2):
        cmds = extract_commands(reply) if not reply.endswith("[stopped]") else []
        if not cmds: break
        outs = []
        for c in cmds:
            o = run_cmd(c)
            if o is not None: outs.append(f"$ {c}\n{o[:2000]}")
        if not outs: break
        history.append({"role": "user", "content": "Command output (Forge really ran this after the user said yes):\n" + "\n\n".join(outs) + "\nNow answer my question using this output. Don't propose the same command again."})
        reply = stream_reply(model, [{"role": "system", "content": system_prompt()}] + history, False)
        history.append({"role": "assistant", "content": reply}); save_chat(history)
    return True

if __name__ == "__main__":
    main()
