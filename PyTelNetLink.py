"""
PyTelNetLink
============
A LAN Telnet discovery tool with a Tkinter GUI.

Scans a local subnet for hosts with an open Telnet port, then lets you
open an interactive session against any discovered host through a
simple terminal-style window.

Notes:
- Uses raw sockets instead of the deprecated `telnetlib` module (removed
  in Python 3.13 / PEP 594), so this runs on current Python versions.
- Telnet option negotiation is handled minimally: this client declines
  (WONT/DONT) every option the server proposes. That's enough for most
  simple devices (routers, switches, lab VMs) but won't satisfy servers
  that require a specific negotiated mode to function.
- Telnet is a cleartext protocol. Use this only against devices/networks
  you control or have permission to test.
"""

from __future__ import annotations

import argparse
import ipaddress
import queue
import re
import socket
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from tkinter import messagebox, simpledialog, ttk
from typing import Callable, List, Optional

# --------------------------------------------------------------------------
# Telnet protocol constants (RFC 854)
# --------------------------------------------------------------------------
IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251

DEFAULT_TELNET_PORT = 23
BASE_IP_PATTERN = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.$")


# --------------------------------------------------------------------------
# Telnet client (raw socket, no deprecated stdlib dependency)
# --------------------------------------------------------------------------
class TelnetClient:
    """Minimal Telnet client over a raw TCP socket."""

    def __init__(self, host: str, port: int = DEFAULT_TELNET_PORT, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(0.5)  # short timeout so reads don't block a reader thread for long

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def send_line(self, data: str) -> None:
        if self.sock is None:
            raise ConnectionError("Not connected")
        if not data.endswith("\n"):
            data += "\n"
        self.sock.sendall(data.encode("ascii", errors="ignore"))

    def read_available(self, max_bytes: int = 4096) -> str:
        """Non-blocking-ish read: returns whatever arrived within the socket timeout, or ''."""
        if self.sock is None:
            return ""
        try:
            raw = self.sock.recv(max_bytes)
        except socket.timeout:
            return ""
        except OSError:
            return ""
        if not raw:
            return ""
        return self._strip_negotiation(raw)

    def _strip_negotiation(self, data: bytes) -> str:
        """Strip IAC option-negotiation sequences and reply declining every option."""
        out = bytearray()
        i = 0
        while i < len(data):
            byte = data[i]
            if byte == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    option = data[i + 2]
                    reply = None
                    if cmd == DO:
                        reply = bytes([IAC, WONT, option])
                    elif cmd == WILL:
                        reply = bytes([IAC, DONT, option])
                    if reply and self.sock is not None:
                        try:
                            self.sock.sendall(reply)
                        except OSError:
                            pass
                    i += 3
                    continue
                if cmd == IAC:
                    out.append(IAC)
                    i += 2
                    continue
                i += 2
                continue
            out.append(byte)
            i += 1
        return out.decode("ascii", errors="ignore")


# --------------------------------------------------------------------------
# Network discovery
# --------------------------------------------------------------------------
def _ip_sort_key(ip: str) -> tuple:
    """Sort key so IPs order numerically (1.1.1.2 before 1.1.1.10)."""
    return tuple(int(part) for part in ip.split("."))


def _probe_host(ip: str, port: int, timeout: float) -> str:
    """
    Attempt a single TCP connect and classify the result:
      - "open"     : connection succeeded, Telnet (or something) is listening.
      - "closed"   : host actively refused the connection - it's up, port isn't.
      - "filtered" : no response within the timeout, or another network error
                     (host unreachable, network unreachable, etc.) - most likely
                     a firewall silently dropping the packets, or the host is down.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return "open"
    except socket.timeout:
        return "filtered"
    except ConnectionRefusedError:
        return "closed"
    except OSError:
        # Covers host/network-unreachable and other connect-time errors. We can't
        # tell a dead host apart from a firewall drop from a plain TCP connect,
        # so both land in "filtered" alongside real timeouts.
        return "filtered"


@dataclass
class ScanSummary:
    """Results of a subnet sweep, broken down by how each host responded."""

    total: int = 0
    open: List[str] = field(default_factory=list)
    closed: List[str] = field(default_factory=list)
    filtered: List[str] = field(default_factory=list)

    @property
    def reachable(self) -> List[str]:
        """Hosts that answered at all, whether or not Telnet was open."""
        return self.open + self.closed

    def as_text(self) -> str:
        return (
            f"Hosts scanned: {self.total}\n"
            f"Hosts reachable: {len(self.reachable)}\n"
            f"Telnet servers found: {len(self.open)}\n"
            f"Closed ports: {len(self.closed)}\n"
            f"Filtered/timeouts: {len(self.filtered)}"
        )


def scan_subnet(
    base_ip: str,
    port: int = DEFAULT_TELNET_PORT,
    timeout: float = 0.5,
    max_workers: int = 100,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    stop_flag: Optional[threading.Event] = None,
) -> ScanSummary:
    """
    Scan base_ip + '1'..'254' on `port`, classifying each host as open/closed/filtered.
    Calls progress_cb(done, total) as results come in. Returns a ScanSummary.
    """
    hosts = [f"{base_ip}{i}" for i in range(1, 255)]
    total = len(hosts)
    summary = ScanSummary(total=total)
    results_lock = threading.Lock()
    progress_lock = threading.Lock()
    completed = 0

    def classify(ip: str) -> None:
        nonlocal completed
        if stop_flag is not None and stop_flag.is_set():
            return
        status = _probe_host(ip, port, timeout)
        with results_lock:
            getattr(summary, status).append(ip)
        if progress_cb:
            with progress_lock:
                completed += 1
                done = completed
            progress_cb(done, total)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(classify, hosts))

    summary.open.sort(key=_ip_sort_key)
    summary.closed.sort(key=_ip_sort_key)
    summary.filtered.sort(key=_ip_sort_key)
    return summary


def is_valid_base_ip(value: str) -> bool:
    if not BASE_IP_PATTERN.match(value):
        return False
    try:
        octets = value.rstrip(".").split(".")
        return all(0 <= int(o) <= 255 for o in octets)
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
@dataclass
class SessionLog:
    host: str
    lines: List[str] = field(default_factory=list)

    def append(self, text: str) -> None:
        if text:
            self.lines.append(text)

    def as_text(self) -> str:
        return "".join(self.lines)


# --------------------------------------------------------------------------
# GUI: Session window
# --------------------------------------------------------------------------
class SessionWindow:
    def __init__(self, master: tk.Misc, client: TelnetClient, host: str):
        self.client = client
        self.host = host
        self.log = SessionLog(host=host)
        self.history: List[str] = []
        self.history_index = -1
        self.out_queue: "queue.Queue[str]" = queue.Queue()
        self.stop_event = threading.Event()

        self.win = tk.Toplevel(master)
        self.win.title(f"Telnet Session — {host}")
        self.win.geometry("720x480")
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        self.text = tk.Text(self.win, wrap=tk.WORD, state=tk.DISABLED, bg="#0d1117", fg="#c9d1d9")
        self.text.pack(expand=True, fill=tk.BOTH, padx=6, pady=(6, 0))

        entry_frame = ttk.Frame(self.win)
        entry_frame.pack(fill=tk.X, padx=6, pady=6)

        self.command_entry = ttk.Entry(entry_frame)
        self.command_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))
        self.command_entry.bind("<Return>", lambda _e: self.send_command())
        self.command_entry.bind("<Up>", self._history_prev)
        self.command_entry.bind("<Down>", self._history_next)
        self.command_entry.focus_set()

        ttk.Button(entry_frame, text="Send", command=self.send_command).pack(side=tk.LEFT)
        ttk.Button(entry_frame, text="Save Log", command=self.save_log).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(entry_frame, text="Close", command=self.close).pack(side=tk.LEFT, padx=(6, 0))

        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self.win.after(100, self._poll_queue)

    def _reader_loop(self) -> None:
        while not self.stop_event.is_set():
            chunk = self.client.read_available()
            if chunk:
                self.out_queue.put(chunk)
            else:
                time.sleep(0.1)

    def _poll_queue(self) -> None:
        try:
            while True:
                chunk = self.out_queue.get_nowait()
                self._append_output(chunk)
        except queue.Empty:
            pass
        if not self.stop_event.is_set():
            self.win.after(100, self._poll_queue)

    def _append_output(self, chunk: str) -> None:
        self.log.append(chunk)
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, chunk)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def send_command(self) -> None:
        command = self.command_entry.get()
        if not command:
            return
        self.command_entry.delete(0, tk.END)
        self.history.append(command)
        self.history_index = len(self.history)

        if command.lower() in ("exit", "quit"):
            self.close()
            return

        self._append_output(f"> {command}\n")
        try:
            self.client.send_line(command)
        except (ConnectionError, OSError) as exc:
            messagebox.showerror("Connection Error", str(exc))
            self.close()

    def _history_prev(self, _event: tk.Event) -> None:
        if not self.history:
            return
        self.history_index = max(0, self.history_index - 1)
        self._set_entry(self.history[self.history_index])

    def _history_next(self, _event: tk.Event) -> None:
        if not self.history:
            return
        self.history_index = min(len(self.history), self.history_index + 1)
        if self.history_index == len(self.history):
            self._set_entry("")
        else:
            self._set_entry(self.history[self.history_index])

    def _set_entry(self, value: str) -> None:
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, value)

    def save_log(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"telnet_session_{self.host}_{timestamp}.txt"
        try:
            with open(filename, "w", encoding="utf-8") as fh:
                fh.write(self.log.as_text())
            messagebox.showinfo("Saved", f"Session log saved to {filename}")
        except OSError as exc:
            messagebox.showerror("Save Failed", str(exc))

    def close(self) -> None:
        self.stop_event.set()
        self.client.close()
        self.win.destroy()


# --------------------------------------------------------------------------
# GUI: Main window
# --------------------------------------------------------------------------
class PyTelNetLinkApp:
    def __init__(self, root: tk.Tk, initial_base_ip: Optional[str] = None):
        self.root = root
        self.root.title("PyTelNetLink")
        self.root.geometry("420x420")
        self.stop_scan = threading.Event()
        self.devices: List[str] = []

        frame = ttk.Frame(root, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Base IP (e.g. 192.168.1.):").pack(anchor=tk.W)
        self.ip_entry = ttk.Entry(frame)
        self.ip_entry.pack(fill=tk.X, pady=(0, 6))
        if initial_base_ip:
            self.ip_entry.insert(0, initial_base_ip)

        self.scan_button = ttk.Button(frame, text="Scan Network", command=self.start_scan)
        self.scan_button.pack(fill=tk.X)

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=254)
        self.progress.pack(fill=tk.X, pady=6)

        self.status_label = ttk.Label(frame, text="Idle")
        self.status_label.pack(anchor=tk.W)

        ttk.Label(frame, text="Discovered devices:").pack(anchor=tk.W, pady=(10, 0))
        self.listbox = tk.Listbox(frame)
        self.listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 6))

        self.connect_button = ttk.Button(frame, text="Connect", command=self.connect_selected, state=tk.DISABLED)
        self.connect_button.pack(fill=tk.X)

        self.summary_label = ttk.Label(frame, text="", justify=tk.LEFT)
        self.summary_label.pack(anchor=tk.W, pady=(8, 0))

    def start_scan(self) -> None:
        base_ip = self.ip_entry.get().strip()
        if not is_valid_base_ip(base_ip):
            messagebox.showerror("Invalid Input", "Enter a base IP like 192.168.1. (with the trailing dot).")
            return

        self.listbox.delete(0, tk.END)
        self.devices = []
        self.connect_button.configure(state=tk.DISABLED)
        self.scan_button.configure(state=tk.DISABLED)
        self.progress["value"] = 0
        self.status_label.configure(text="Scanning...")
        self.summary_label.configure(text="")

        thread = threading.Thread(target=self._run_scan, args=(base_ip,), daemon=True)
        thread.start()

    def _run_scan(self, base_ip: str) -> None:
        def progress_cb(done: int, total: int) -> None:
            self.root.after(0, self._update_progress, done, total)

        summary = scan_subnet(base_ip, progress_cb=progress_cb, stop_flag=self.stop_scan)
        self.root.after(0, self._scan_complete, summary)

    def _update_progress(self, done: int, total: int) -> None:
        self.progress["value"] = done
        self.status_label.configure(text=f"Scanning... {done}/{total}")

    def _scan_complete(self, summary: ScanSummary) -> None:
        # Connect list behavior is unchanged: only Telnet-open hosts are selectable.
        self.devices = summary.open
        self.scan_button.configure(state=tk.NORMAL)
        self.status_label.configure(
            text=f"Found {len(summary.open)} device(s)." if summary.open else "No devices found."
        )
        for ip in summary.open:
            self.listbox.insert(tk.END, ip)
        self.connect_button.configure(state=tk.NORMAL if summary.open else tk.DISABLED)
        self.summary_label.configure(text=summary.as_text())

    def connect_selected(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo("Select a Device", "Choose a discovered device first.")
            return
        host = self.devices[selection[0]]

        port = simpledialog.askinteger("Port", "Port:", initialvalue=DEFAULT_TELNET_PORT, parent=self.root)
        if port is None:
            return
        username = simpledialog.askstring("Username", "Username (leave blank if none):", parent=self.root)
        password = simpledialog.askstring("Password", "Password (leave blank if none):", parent=self.root, show="*")

        client = TelnetClient(host, port=port)
        try:
            client.connect()
        except OSError as exc:
            messagebox.showerror("Connection Failed", str(exc))
            return

        if username:
            client.send_line(username)
        if password:
            time.sleep(0.3)
            client.send_line(password)

        SessionWindow(self.root, client, host)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LAN Telnet discovery tool with a GUI.")
    parser.add_argument(
        "--subnet",
        help="Pre-fill the base IP to scan, e.g. 192.168.1.",
        default=None,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.subnet and not is_valid_base_ip(args.subnet):
        raise SystemExit(f"Invalid --subnet value: {args.subnet!r} (expected form like 192.168.1.)")

    root = tk.Tk()
    PyTelNetLinkApp(root, initial_base_ip=args.subnet)
    root.mainloop()


if __name__ == "__main__":
    main()
