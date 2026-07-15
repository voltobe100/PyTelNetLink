# PyTelNetLink

A Python tool for discovering devices on a local network with open Telnet ports (23) and connecting to them through a Tkinter GUI. Built to make ad-hoc Telnet access to LAN devices (routers, switches, IoT devices, lab VMs) faster than manually tracking IPs.

## Features

- **Fast parallel discovery** — thread-pooled scan of a /24 subnet with a live progress bar
- **Real Telnet protocol handling** — raw-socket client that correctly strips IAC option-negotiation sequences instead of leaking control bytes into the terminal
- **GUI session window** — command history (↑/↓), scrollback, and one-click session log export
- **Optional authentication** — sends username/password automatically if the device prompts for them
- **CLI shortcut** — `--subnet` flag to pre-fill the base IP and skip typing it every run
- **No deprecated dependencies** — does not use `telnetlib` (removed in Python 3.13); works on current Python versions
- **Cross-platform** — Windows, Linux, macOS

## Requirements

- Python 3.10+
- Tkinter (see installation note below — it does **not** install via `pip`)

## Installation

```bash
git clone https://github.com/voltobe100/PyTelNetLink.git
cd PyTelNetLink
```

Tkinter ships with the standard Python installer on Windows and macOS. On most Linux distributions it's a separate system package:

```bash
# Debian/Ubuntu
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

Then run:

```bash
python pytelnetlink.py
# or pre-fill the subnet:
python pytelnetlink.py --subnet 192.168.1.
```

## Usage

1. Enter your network's base IP (e.g. `192.168.1.`) and click **Scan Network**. A progress bar tracks the sweep across `.1`–`.254`.
2. Select a discovered device from the list and click **Connect**.
3. Enter the port (default `23`) and credentials, if the device requires them.
4. Send commands in the session window — use ↑/↓ to recall previous commands.
5. Click **Save Log** to export the full session transcript to a text file, or type `exit`/`quit` to close the session.

## Security Note

Telnet transmits everything — including credentials — in **cleartext**, and this client's option negotiation simply declines every option a server proposes rather than fully implementing RFC 854. It's intended for lab environments, personal networks, and legacy devices you control, not for use over untrusted networks or against systems you don't have permission to access. Where possible, prefer SSH over Telnet for anything beyond local testing.

## Architecture

- `TelnetClient` — raw-socket Telnet client with IAC negotiation stripping
- `scan_subnet()` — thread-pooled port scanner with progress callback
- `SessionWindow` — GUI session view, backed by a background reader thread + queue so the UI never blocks on network I/O
- `PyTelNetLinkApp` — main discovery window

## Future Improvements

- [ ] IPv6 / arbitrary CIDR support (currently assumes a /24)
- [ ] Package as a standalone executable
- [ ] File upload support over Telnet

## Contributing

Forks and pull requests are welcome.

## License

MIT License — free to use, modify, and distribute.

---

Questions? Reach out at [vaibhavc.pgolchha@gmail.com](mailto:vaibhavc.pgolchha@gmail.com)
