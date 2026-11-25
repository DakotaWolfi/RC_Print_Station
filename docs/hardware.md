# Hardware bring-up

1. Boot the backed-up PT35 Pi. Run `python3 station.py diagnose` and inspect active PT35 services. Do not disable SSH or networking.
2. Connect Epson on dedicated Ethernet; inspect existing network manager and printer address before choosing a static IP or isolated DHCP pool.
3. Connect Nextion using its documented 5 V supply and verify UART logic compatibility before attaching GPIO. Test at 9600 first; configured baud may differ. Do not connect to an active serial console.
4. When the tester arrives, record manufacturer, model, firmware, connector and USB enumeration. Prefer documented read-only export. Preserve original measurements and verdict, never infer a safety pass.
5. Port to Orange Pi using a fresh OS and configurable UART/network settings.
