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


    def get_mousebtn_events(self, device):
        try:
            events = list(device.read())
            for event in events:
                if event.type==evdev.ecodes.EV_KEY:
                    yield event
        except IOError:
            pass
            #print('Looks like the device was idle since the last read')

    def update(self):
        #poll inputs
        def is_key(kevent, code):
            #checks wether a keyevent-object has the specified KeyCode such as "BTN_START"
            kcode = kevent.keycode
            iskey = False
            for cd in kcode:
                if cd == code:
                    iskey = True
            return iskey or kcode == code

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
            #call callbacks for each type of key and store key state information
            any = True
            keyevent = evdev.categorize(event)
            events.append(keyevent)
            if is_key(keyevent, 'BTN_A') or is_key(keyevent, 'BTN_B') or is_key(keyevent, 'BTN_C') or is_key(keyevent, 'BTN_X') or is_key(keyevent, 'BTN_Y') or is_key(keyevent, 'BTN_Z'):
                self.on_red_buttons(keyevent.keystate)
            if is_key(keyevent, 'BTN_SELECT'):
                self.on_select(keyevent.keystate)
                self.select = keyevent.keystate
            if is_key(keyevent, 'BTN_START'):
                self.on_start(keyevent.keystate)
                self.start = keyevent.keystate
            if is_key(keyevent, 'BTN_A'):
                self.on_a(keyevent.keystate)
                self.a = keyevent.keystate
            if is_key(keyevent, 'BTN_B'):
                self.on_b(keyevent.keystate)
                self.b = keyevent.keystate
            if is_key(keyevent, 'BTN_C'):
                self.on_c(keyevent.keystate)
                self.c = keyevent.keystate
            if is_key(keyevent, 'BTN_X'):
                self.on_x(keyevent.keystate)
                self.x = keyevent.keystate
            if is_key(keyevent, 'BTN_Y'):
                self.on_y(keyevent.keystate)
                self.y = keyevent.keystate
            if is_key(keyevent, 'BTN_Z'):
                self.on_z(keyevent.keystate)
                self.z = keyevent.keystate
            if is_key(keyevent, 'BTN_DPAD_RIGHT'):
                self.on_right(keyevent.keystate)
                self.right = keyevent.keystate
            if is_key(keyevent, 'BTN_DPAD_LEFT'):
                self.on_left(keyevent.keystate)
                self.left = keyevent.keystate
            if is_key(keyevent, 'BTN_DPAD_DOWN'):
                #down/up is switched on piboy
                self.on_up(keyevent.keystate)
                self.up = keyevent.keystate
            if is_key(keyevent, 'BTN_DPAD_UP'):
                self.on_down(keyevent.keystate)
                self.down = keyevent.keystate
            if is_key(keyevent, 'BTN_TL'):
                #shoulder left/right is switched on piboy
                self.on_right_shoulder(keyevent.keystate)
                self.right_shoulder = keyevent.keystate
            if is_key(keyevent, 'BTN_TR'):
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
