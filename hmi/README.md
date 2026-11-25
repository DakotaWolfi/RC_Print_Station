# Portrait Nextion HMI prototype

Use the existing dark 480 x 800 HMI template. In Nextion Editor use Tools > Font Generator to create a 24 px ISO-8859-1 font (font ID 0), add it to the project's Fonts resources, then compile and upload to the display. No native page controls are required. Keep startup baud at 9600. The Pi draws the screens using xstr/fill and handles sendxy touch release events. The UI is experimental and has not yet been tested on the display. Stop other software using the UART first.

```sh
sudo apt install python3-serial
python3 nextion_ui.py --port /dev/serial0 --baud 9600 --host 169.254.223.252
```

Use Ctrl+C to stop. All reports are simulations, never safety certificates. Printer address is the confirmed development address but can change. Rendering at 9600 baud may be slow. Native editable multi-page HMI remains a future option.
