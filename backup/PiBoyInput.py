import os
import evdev

class PBInput():

    def __init__(self, *args, **kwargs):
        #Init Controller Input
        self.printany = False
        #search for PiBoy Gamecontroller
        for dp in evdev.list_devices():
            device = evdev.InputDevice(dp)
            if "PiBoy" in device.name:
                self.device = device

        self.a = False
        self.b = False
        self.c = False
        self.x = False
        self.y = False
        self.z = False
        self.up = False
        self.down = False
        self.left = False
        self.right = False
        self.start = False
        self.select = False
        self.left_shoulder = False
        self.right_shoulder = False
        self.red_button = False
        self.stopping = False



    def get_mousebtn_events(self, device):
        try:
            events = list(device.read())
            for event in events:
                if event.type==evdev.ecodes.EV_KEY:
                    yield event
        except IOError:
            pass
            #print('Looks like the device was idle since the last read')
    
    def listen(self):
        #poll inputs
        self.update_callback()
        any = False
        events = []
        for event in self.device.read_loop():
            #call callbacks for each type of key and store key state information
            any = True
            if event.type==evdev.ecodes.EV_KEY:
                keyevent = evdev.categorize(event)
                keycode = keyevent.keycode
                events.append(keycode) #store events for any-callback lateron
                if 'BTN_A' in keycode or 'BTN_B' in keycode or 'BTN_C' in keycode or 'BTN_X' in keycode or 'BTN_Y' in keycode or 'BTN_Z' in keycode:
                    self.on_red_buttons(keyevent.keystate)
                if 'BTN_SELECT' in keycode:
                    self.on_select(keyevent.keystate)
                    self.select = keyevent.keystate
                if 'BTN_START' in keycode:
                    self.on_start(keyevent.keystate)
                    self.start = keyevent.keystate
                if 'BTN_A' in keycode:
                    self.on_a(keyevent.keystate)
                    self.a = keyevent.keystate
                if 'BTN_B' in keycode:
                    self.on_b(keyevent.keystate)
                    self.b = keyevent.keystate
                if 'BTN_C' in keycode:
                    self.on_c(keyevent.keystate)
                    self.c = keyevent.keystate
                if 'BTN_X' in keycode:
                    self.on_x(keyevent.keystate)
                    self.x = keyevent.keystate
                if 'BTN_Y' in keycode:
                    self.on_y(keyevent.keystate)
                    self.y = keyevent.keystate
                if 'BTN_Z' in keycode:
                    self.on_z(keyevent.keystate)
                    self.z = keyevent.keystate
                if 'BTN_DPAD_RIGHT' in keycode:
                    self.on_right(keyevent.keystate)
                    self.right = keyevent.keystate
                if 'BTN_DPAD_LEFT' in keycode:
                    self.on_left(keyevent.keystate)
                    self.left = keyevent.keystate
                if 'BTN_DPAD_DOWN' in keycode:
                    #down/up is switched on piboy
                    self.on_up(keyevent.keystate)
                    self.up = keyevent.keystate
                if 'BTN_DPAD_UP' in keycode:
                    self.on_down(keyevent.keystate)
                    self.down = keyevent.keystate
                if 'BTN_TL' in keycode:
                    #shoulder left/right is switched on piboy
                    self.on_right_shoulder(keyevent.keystate)
                    self.right_shoulder = keyevent.keystate
                if 'BTN_TR' in keycode:
                    self.on_left_shoulder(keyevent.keystate)
                    self.left_shoulder = keyevent.keystate
                self.red_button = self.a or self.b or self.c or self.x or self.y or self.z
                self.update_callback()
                if self.stopping:
                    break

    def stop(self):
        self.stopping = True

    def update(self):
        #poll inputs
        def get_mousebtn_events(device):
            try:
                events = list(device.read())
                for event in events:
                    if event.type==evdev.ecodes.EV_KEY:
                        yield event
            except IOError:
                pass
                #print('Looks like the device was idle since the last read')

        any = False
        events = []
        for event in self.get_mousebtn_events(self.device):
        #for event in self.device.active_keys(verbose=True):
            #call callbacks for each type of key and store key state information
            any = True
            keyevent = evdev.categorize(event)
            keycode = keyevent.keycode
            events.append(keycode) #store events for any-callback lateron
            if 'BTN_A' in keycode or 'BTN_B' in keycode or 'BTN_C' in keycode or 'BTN_X' in keycode or 'BTN_Y' in keycode or 'BTN_Z' in keycode:
                self.on_red_buttons(keyevent.keystate)
            if 'BTN_SELECT' in keycode:
                self.on_select(keyevent.keystate)
                self.select = keyevent.keystate
            if 'BTN_START' in keycode:
                self.on_start(keyevent.keystate)
                self.start = keyevent.keystate
            if 'BTN_A' in keycode:
                self.on_a(keyevent.keystate)
                self.a = keyevent.keystate
            if 'BTN_B' in keycode:
                self.on_b(keyevent.keystate)
                self.b = keyevent.keystate
            if 'BTN_C' in keycode:
                self.on_c(keyevent.keystate)
                self.c = keyevent.keystate
            if 'BTN_X' in keycode:
                self.on_x(keyevent.keystate)
                self.x = keyevent.keystate
            if 'BTN_Y' in keycode:
                self.on_y(keyevent.keystate)
                self.y = keyevent.keystate
            if 'BTN_Z' in keycode:
                self.on_z(keyevent.keystate)
                self.z = keyevent.keystate
            if 'BTN_DPAD_RIGHT' in keycode:
                self.on_right(keyevent.keystate)
                self.right = keyevent.keystate
            if 'BTN_DPAD_LEFT' in keycode:
                self.on_left(keyevent.keystate)
                self.left = keyevent.keystate
            if 'BTN_DPAD_DOWN' in keycode:
                #down/up is switched on piboy
                self.on_up(keyevent.keystate)
                self.up = keyevent.keystate
            if 'BTN_DPAD_UP' in keycode:
                self.on_down(keyevent.keystate)
                self.down = keyevent.keystate
            if 'BTN_TL' in keycode:
                #shoulder left/right is switched on piboy
                self.on_right_shoulder(keyevent.keystate)
                self.right_shoulder = keyevent.keystate
            if 'BTN_TR' in keycode:
                self.on_left_shoulder(keyevent.keystate)
                self.left_shoulder = keyevent.keystate
            self.red_button = self.a or self.b or self.c or self.x or self.y or self.z
        if any:
            self.on_any(events)
            
    def set_callback(self, cb_type, cb):
        if cb_type.upper() == 'ANY':
            self.on_any = cb
        if cb_type.upper() == 'A':
            self.on_a = cb
        elif cb_type.upper() == 'B':
            self.on_b = cb
        elif cb_type.upper() == 'C':
            self.on_c = cb
        elif cb_type.upper() == 'X':
            self.on_x = cb
        elif cb_type.upper() == 'Y':
            self.on_y = cb
        elif cb_type.upper() == 'Z':
            self.on_z = cb
        elif cb_type.upper() == 'UP':
            self.on_up = cb
        elif cb_type.upper() == 'DOWN':
            self.on_down = cb
        elif cb_type.upper() == 'LEFT':
            self.on_left = cb
        elif cb_type.upper() == 'RIGHT':
            self.on_right = cb
        elif cb_type.upper() == 'START':
            self.on_start = cb
        elif cb_type.upper() == 'SELECT':
            self.on_select = cb
        elif cb_type.upper() == 'RIGHT_SHOULDER':
            self.on_right_shoulder = cb
        elif cb_type.upper() == 'LEFT_SHOULDER':
            self.on_left_shoulder = cb
        elif cb_type.upper() == 'RED_BUTTONS':
            self.on_red_buttons = cb

    #dummy callbacks
    def on_any(self, keyevents):
        if self.printany:
            #print any key pressed (for debug)
            message = ""
            for k in keyevents:
                message = message + str(k.keycode)
            print(message)
    def on_a(self, pressed):
        print("Input: A - " + str(pressed))
    def on_b(self, pressed):
        print("Input: B - " + str(pressed))
    def on_c(self, pressed):
        print("Input: C - " + str(pressed))
    def on_x(self, pressed):
        print("Input: X - " + str(pressed))
    def on_y(self, pressed):
        print("Input: Y - " + str(pressed))
    def on_z(self, pressed):
        print("Input: Z - " + str(pressed))
    def on_up(self, pressed):
        print("Input: UP - " + str(pressed))
    def on_down(self, pressed):
        print("Input: DOWN - " + str(pressed))
    def on_left(self, pressed):
        print("Input: LEFT - " + str(pressed))
    def on_right(self, pressed):
        print("Input: RIGHT - " + str(pressed))
    def on_start(self, pressed):
        print("Input: START - " + str(pressed))
    def on_select(self, pressed):
        print("Input: SELECT - " + str(pressed))
    def on_right_shoulder(self, pressed):
        print("Input: RIGHT SHOULDER - " + str(pressed))
    def on_left_shoulder(self, pressed):
        print("Input: LEFT SHOULDER - " + str(pressed))
    def on_red_buttons(self, pressed):
        print("Any Red Button Pressed - " + str(pressed))
 

if __name__ == "__main__":
    ### TESTER/EXAMPLE ###
    class EventHandler():
        def __init__(self, *args, **kwargs):
            pass
        def on_a(self, pressed):
            print("Input A - pressed:" + str(pressed))
        def on_start(self, pressed):
            self.done=True

    eh = EventHandler()
    dev = PBInput()
    dev.printany = True
    dev.set_callback("A", eh.on_a)
    dev.set_callback("start", eh.on_start)

    eh.done = False
    while not eh.done:
        dev.update()
