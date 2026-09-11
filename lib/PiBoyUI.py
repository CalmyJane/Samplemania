import math
import os
import pygame
from pygame import draw
from pygame.locals import *

from config import asset


def load_image(path):
    """Load an image converted to the display's pixel format. Unconverted
    images are converted again on every blit, which is slow on the Pi -
    and drawing time is time the audio thread may be waiting for the GIL."""
    image = pygame.image.load(path)
    try:
        return image.convert_alpha()
    except pygame.error:        # no display yet
        return image


class Button(pygame.sprite.Sprite):
    def __init__(self, position, on_img, off_img):
        self.pressed = False
        self.position = position
        self.off_image = load_image(off_img)
        self.on_image = load_image(on_img)
        pygame.sprite.Sprite.__init__(self)
        self.set_state(False)

    def set_state(self, pressed):
        self.pressed = pressed
        if pressed:
            self.image = self.on_image
        else:
            self.image = self.off_image
        self.rect = self.image.get_rect()
        self.rect.x = self.position[0]
        self.rect.y = self.position[1]

class ButtonRow(pygame.sprite.Group):
    def __init__(self, position):
        self.position = position
        pygame.sprite.Group.__init__(self)
        self.spritelist = []
        for i in range(3):
            for j in range(2):
                btn = Button((i*50 + self.position[0], j*50 + self.position[1] - i*15), asset("button_on.png"), asset("button_off.png"))
                self.add(btn)
                self.spritelist.append(btn)

    def set_button(self, index, pressed):
        self.spritelist[index].set_state(pressed)

class ListView():
    def __init__(self, pos, fontsize, spacing, *args, **kwargs):
        self.pos = pos
        self.spacing = spacing #spacing between text labels
        self.fontsize = fontsize
        self.texts = []
        for i in range(6):
            position = (self.pos[0], i*(self.spacing + self.fontsize)+self.pos[1])
            self.texts.append(Text("Test" + str(i) + ".wav", position, self.fontsize, Color('black'), Color('red')))

    def draw(self, screen):
        for txt in self.texts:
            txt.draw(screen)

    def set_strings(self, strings):
        for i, text in enumerate(self.texts):
            text.set_text(strings[i])

    def highlight(self, index, high):
        self.texts[index].bgcolor = (200,20,20) if high else (250, 20, 20)

class Background:
    def __init__(self):
        self.height = 480
        self.width = 640
        self.size = 25
        self.image = self._render()

    def _render(self):
        """Draw the line pattern and frame once; draw() only blits the result."""
        surface = pygame.Surface((self.width, self.height))
        surface.fill(Color('black'))
        for i in range ( 0, self.width, self.size ):
            pygame.draw.line ( surface, ( 0, 250-i/25, 0 ), ( 0, i ), ( i, self.height ), 1 )
            pygame.draw.line ( surface, ( 200+i/15, 0, 0 ), ( i, 0 ), ( self.width, i ), 1 )
        frame = pygame.image.load(asset('background.png'))
        surface.blit(frame, frame.get_rect())
        try:
            return surface.convert()
        except pygame.error:    # no display yet
            return surface

    def draw(self, screen):
        screen.blit(self.image, (0, 0))

class Dpad():
    def __init__(self,pos, *args, **kwargs):
        self.pos = pos
        self.bg_img = load_image(asset('cross_bg.png'))
        self.up_on_img = load_image(asset('cross_up_on.png'))
        self.up_off_img = load_image(asset('cross_up_off.png'))
        self.down_on_img = load_image(asset('cross_down_on.png'))
        self.down_off_img = load_image(asset('cross_down_off.png'))
        self.left_on_img = load_image(asset('cross_left_on.png'))
        self.left_off_img = load_image(asset('cross_left_off.png'))
        self.right_on_img = load_image(asset('cross_right_on.png'))
        self.right_off_img = load_image(asset('cross_right_off.png'))
        DEFAULT_IMAGE_SIZE = (80,80)
        self.bg_img = pygame.transform.scale(self.bg_img, DEFAULT_IMAGE_SIZE)
        self.up_on_img = pygame.transform.scale(self.up_on_img, DEFAULT_IMAGE_SIZE)
        self.up_off_img = pygame.transform.scale(self.up_off_img, DEFAULT_IMAGE_SIZE)
        self.down_on_img = pygame.transform.scale(self.down_on_img, DEFAULT_IMAGE_SIZE)
        self.down_off_img = pygame.transform.scale(self.down_off_img, DEFAULT_IMAGE_SIZE)
        self.left_on_img = pygame.transform.scale(self.left_on_img, DEFAULT_IMAGE_SIZE)
        self.left_off_img = pygame.transform.scale(self.left_off_img, DEFAULT_IMAGE_SIZE)
        self.right_on_img = pygame.transform.scale(self.right_on_img, DEFAULT_IMAGE_SIZE)
        self.right_off_img = pygame.transform.scale(self.right_off_img, DEFAULT_IMAGE_SIZE)
        self.up = False
        self.down = False
        self.left = False
        self.right = False
        self.rect = self.bg_img.get_rect().move(self.pos)

    def set_values(self, up, down, left, right):
        self.up = up
        self.down = down
        self.left = left
        self.right = right

    def draw(self, screen):
        up = self.up_on_img if self.up else self.up_off_img
        down = self.down_on_img if self.down else self.down_off_img
        left = self.left_on_img if self.left else self.left_off_img
        right = self.right_on_img if self.right else self.right_off_img
        screen.blit(self.bg_img, self.rect)
        screen.blit(up, self.rect)
        screen.blit(down, self.rect)
        screen.blit(left, self.rect)
        screen.blit(right, self.rect)


class Text:
    """Create a text object."""
    def __init__(self, text, pos, fontsize, color, bgcolor, **options):
        self.text = text
        self.pos = pos
        self.fontsize = fontsize
        self.color = color
        self.bgcolor = bgcolor
        self.padding = options.get('padding', 1)   # bg margin around the text
        self.fontname = None
        self.set_font()
        self.render()

    def set_font(self):
        """Set the font from its name and size."""
        self.font = pygame.font.Font(self.fontname, self.fontsize)

    def render(self):
        """Render the text into an image."""
        self.img = self.font.render(self.text, True, self.color)
        self.rect = self.img.get_rect()
        self.rect.x = self.pos[0]
        self.rect.y = self.pos[1]

    def set_text(self, text):
        """Change the string, re-rendering only when it actually differs.
        Rendering a font every frame is wasted work on the Pi."""
        if text != self.text:
            self.text = text
            self.render()

    def set_color(self, color):
        if color != self.color:
            self.color = color
            self.render()

    def draw(self, screen):
        """Draw the text image to the screen."""
        if self.bgcolor != None:
            pygame.draw.rect(screen, self.bgcolor, self.rect.inflate(self.padding * 2, self.padding * 2))
        screen.blit(self.img, self.rect)


class Meter:
    """Horizontal level meter with peak hold and a clip led.

    Fed with 0..1 linear values but drawn on a dB scale, because linear looks
    dead below half scale - which is where most of a spoken take sits.
    """
    FLOOR_DB = -48.0

    def __init__(self, pos, size=(440, 34)):
        self.pos = pos
        self.size = size
        self.rms = 0.0
        self.peak = 0.0
        self.peak_hold = 0.0
        self.hold_frames = 0
        self.clipped = False

    def _to_db_fraction(self, value):
        if value <= 0.0:
            return 0.0
        db = 20.0 * math.log10(max(value, 1e-6))
        if db <= self.FLOOR_DB:
            return 0.0
        return min(1.0, (db - self.FLOOR_DB) / (0.0 - self.FLOOR_DB))

    def set_values(self, rms, peak, clipped=False):
        self.rms = rms
        self.peak = peak
        if clipped:
            self.clipped = True
        if peak >= self.peak_hold:
            self.peak_hold = peak
            self.hold_frames = 30      # ~1s at 30fps
        elif self.hold_frames > 0:
            self.hold_frames -= 1
        else:
            self.peak_hold = max(0.0, self.peak_hold - 0.02)

    def reset(self):
        self.rms = 0.0
        self.peak = 0.0
        self.peak_hold = 0.0
        self.hold_frames = 0
        self.clipped = False

    def draw(self, screen):
        x, y = self.pos
        w, h = self.size

        pygame.draw.rect(screen, (20, 20, 20), (x, y, w, h))
        pygame.draw.rect(screen, (90, 90, 90), (x, y, w, h), 2)

        filled = int(self._to_db_fraction(self.rms) * (w - 4))
        for i in range(0, filled, 4):
            frac = i / float(max(1, w - 4))
            if frac > 0.92:
                color = (230, 40, 40)
            elif frac > 0.78:
                color = (230, 200, 40)
            else:
                color = (40, 220, 80)
            pygame.draw.rect(screen, color, (x + 2 + i, y + 2, 3, h - 4))

        hold = int(self._to_db_fraction(self.peak_hold) * (w - 4))
        if hold > 0:
            pygame.draw.rect(screen, (255, 255, 255), (x + 2 + min(hold, w - 6), y + 2, 2, h - 4))

        # clip led
        led = (255, 40, 40) if self.clipped else (60, 20, 20)
        pygame.draw.rect(screen, led, (x + w + 10, y, h, h))
        pygame.draw.rect(screen, (90, 90, 90), (x + w + 10, y, h, h), 2)


class ConfirmDialog:
    """Modal yes/no box drawn over whatever mode is active."""

    SIZE = (520, 180)

    def __init__(self, message="", detail=""):
        w, h = self.SIZE
        self.rect = pygame.Rect((640 - w) // 2, (480 - h) // 2, w, h)
        x, y = self.rect.x, self.rect.y

        self.overlay = pygame.Surface((640, 480))
        self.overlay.set_alpha(190)
        self.overlay.fill((0, 0, 0))

        self.title = Text(message, (x + 24, y + 22), 36, Color('white'), None)
        self.detail = Text(detail, (x + 24, y + 68), 26, (200, 200, 200), None)
        self.hint = Text("A = YES     B = NO", (x + 24, y + 122), 30, (255, 210, 80), None)

    def draw(self, screen):
        screen.blit(self.overlay, (0, 0))
        pygame.draw.rect(screen, (25, 25, 30), self.rect)
        pygame.draw.rect(screen, (230, 60, 60), self.rect, 3)
        self.title.draw(screen)
        if self.detail.text:
            self.detail.draw(screen)
        self.hint.draw(screen)
