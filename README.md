# Telnet Client with GUI and Auto Discovery

This Python project allows you to connect to any device in your local network via **Telnet Protocol**. It comes with a GUI interface to make the process easier and has an automatic device discovery feature to find devices with open **Telnet ports (23)**.

## 🚀 Features

- ✅ **Automatic Device Discovery:** Scans your local network to find devices with open Telnet ports.
- ✅ **GUI Interface:** Provides a graphical interface to interact with the target device.
- ✅ **Command Execution:** Allows you to execute commands on the target device and view the output in real-time.
- ✅ **Username/Password Support:** Handles authentication if required.
- ✅ **Cross-Platform:** Works on Windows, Linux, and MacOS.

## 📜 Requirements

- Python 3.10 or above
- tkinter (built-in Python library)

## 📂 Installation

1. Clone the repository:

```bash
git clone https://github.com/your-username/telnet-client-gui.git
cd telnet-client-gui
```

2. Install any missing Python libraries (if not already installed):

```bash
pip install tkinter
```

3. Run the script:

```bash
python telnet_client.py
```

## 💻 Usage

1. **Enter your Network Base IP** like `192.168.1.`.
2. The program will scan all IPs from **192.168.1.1 to 192.168.1.255**.
3. Select the device from the discovered devices.
4. Enter **Username/Password** (if required).
5. Use the terminal interface to send commands.
6. Type `exit` or `quit` to close the connection.

## 📜 Example Output

```
[+] Scanning for devices in the network...
[+] Device found: 192.168.1.10
[+] Device found: 192.168.1.11

Select device index:
[0] 192.168.1.10
[1] 192.168.1.11
```

## 🎉 Future Improvements

- ✅ Save session logs in a text file.
- ✅ Package it as an executable (.exe) file.
- ✅ Add a file upload feature via Telnet.

## 🤝 Contributing

If you'd like to contribute, feel free to fork the repository and submit a pull request.

## 📝 License

This project is licensed under the **MIT License**. You can use, modify, and distribute it freely.

---

💬 **Need Help?** Feel free to contact me at [vaibhavgolchha@proton.me](mailto:vaibhavgolchha@proton.me)
