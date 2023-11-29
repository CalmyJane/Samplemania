# Samplemania
Turn your PiBoy DMG into a mobile Sampler.

Custom python code to be used on a PiBoy DMG with a Raspberry Pi 3 and the default RetroPie Image with PiBoy Scripts installed.

This code uses evdev to query the Input Controls of the PiBoy and pygame to create a graphical user interface.

To run this code, you need to register python files as plugins.

Step by Step setup:
1. Setup your PiBoy DMG as described here: https://resources.experimentalpi.com/the-complete-piboy-dmg-getting-started-guide/
2. Connect PiBoy to your Wifi: https://resources.experimentalpi.com/piboy-dmg-wifi-setup/
3. Connect to your PiBoy DMG by typing \\retropie in your Explorer while the device is turned on an connected to wifi
4. Add some ROMs for testing, you can find them on google ;)
5. Add a new "System" to your EmulationStation, this is a new type of ROMs you want to load, make the file type ".py" and the command "sudo python3 %ROM%": https://retropie.org.uk/docs/Add-a-New-System-in-EmulationStation/
You can basically also add all kind of files or direct shell script this way. Be aware, that this as always is a security risk ;)
6. Add the python file from this repo to the folder you specified for the system on \\retropie
7. Start your PiBoy and in EmulationStation instread of "GameBoy" or "GameBoy Color" select "python" and select Samplemania

I hope you find other ways to play around here, this was a really fun project, and can potentially be used to develop custom games for the PiBoy as well :D