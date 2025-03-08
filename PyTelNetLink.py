import telnetlib
import time
import socket
import threading
import tkinter as tk
from tkinter import simpledialog, messagebox

def discover_devices(base_ip):
    discovered_devices = []

    def ping_device(ip):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex((ip, 23))
            if result == 0:
                discovered_devices.append(ip)
            sock.close()
        except:
            pass

    threads = []
    for i in range(1, 255):
        ip = f"{base_ip}{i}"
        thread = threading.Thread(target=ping_device, args=(ip,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return discovered_devices


def telnet_connect(host, port, username, password):
    try:
        tn = telnetlib.Telnet(host, port)
        if username and password:
            tn.read_until(b"login: ")
            tn.write(username.encode('ascii') + b"\n")
            tn.read_until(b"Password: ")
            tn.write(password.encode('ascii') + b"\n")

        output_window = tk.Tk()
        output_window.title(f"Telnet Session - {host}")
        text = tk.Text(output_window, wrap=tk.WORD)
        text.pack(expand=True, fill=tk.BOTH)

        def send_command():
            command = command_entry.get()
            if command.lower() in ['exit', 'quit']:
                tn.close()
                output_window.destroy()
                return

            tn.write(command.encode('ascii') + b"\n")
            time.sleep(1)
            output = tn.read_very_eager().decode('ascii')
            text.insert(tk.END, output + "\n")

        command_entry = tk.Entry(output_window)
        command_entry.pack(fill=tk.X)
        send_button = tk.Button(output_window, text="Send", command=send_command)
        send_button.pack()

        output_window.mainloop()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to connect: {e}")


def main():
    root = tk.Tk()
    root.withdraw()

    base_ip = simpledialog.askstring("Input", "Enter your network base IP (e.g., 192.168.1.):")
    devices = discover_devices(base_ip)

    if not devices:
        messagebox.showinfo("Info", "No devices found.")
        return

    selected_device = simpledialog.askinteger("Select Device", "Select device index:\n" + "\n".join([f"[{i}] {d}" for i, d in enumerate(devices)]))
    if selected_device is None or selected_device >= len(devices):
        return

    device_ip = devices[selected_device]
    port = simpledialog.askinteger("Port", "Enter port (default 23):", initialvalue=23)
    username = simpledialog.askstring("Username", "Enter username (if any):")
    password = simpledialog.askstring("Password", "Enter password (if any):")

    telnet_connect(device_ip, port, username, password)

if __name__ == "__main__":
    main()
