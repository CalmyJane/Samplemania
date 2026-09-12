"""Widgets and the look of the app.

Everything here is built for the Pi: surfaces are pre-rendered and
`convert()`ed once, fonts are cached, and nothing is re-rendered while it
hasn't changed. Drawing holds the GIL, which the audio thread needs whenever a
sample ends - so a frame has to stay a handful of blits.
"""

import math
import pygame
from pygame import draw
from pygame.locals import *

import config
from config import asset

SCREEN_W = 640
SCREEN_H = 480

# The header (logo + preset) is deliberately shallow: everything below it
# belongs to the six sample names, which is what you read on stage.
HEADER_H = 52

# The accent of the whole app is the dark red-purple of the Game Boy buttons.
# GB is the line colour, GB_BRIGHT a lit button, GB_DIM a quiet one.
GB_BRIGHT = (214, 74, 128)
GB = (158, 48, 92)
GB_DIM = (96, 30, 58)
GB_TEXT = (246, 214, 228)
# The slot markings - button letter, number in the preset, page counter - are
# white on every background, so they read the same lit or not.
MARK = (255, 255, 255)


## FONTS ##

_FONT_CACHE = {}


def get_font(size, bold=False):
    """Fonts are expensive to build and only a few sizes are in use, so they
    are made once and kept."""
    key = (size, bold)
    font = _FONT_CACHE.get(key)
    if font is None:
        font = pygame.font.Font(None, size)
        font.set_bold(bold)
        _FONT_CACHE[key] = font
    return font


def load_image(path):
    """Load an image converted to the display's pixel format. Unconverted
    images are converted again on every blit, which is slow on the Pi -
    and drawing time is time the audio thread may be waiting for the GIL."""
    image = pygame.image.load(path)
    try:
        return image.convert_alpha()
    except pygame.error:        # no display yet
        return image


## TEXT FITTING ##

# A sample name is broken at these characters first; the separator stays at
# the end of the word, so "kick_hard_01" reads as "kick_ / hard_01".
_BREAKS = " _-."


def split_name(text):
    """Break a sample name into the pieces a line may end after.

    Sample names rarely have spaces in them, so a capital letter inside a
    word counts as a break too: "BigFatKick" goes to "Big" "Fat" "Kick". Only
    one that follows a small letter or a digit does, so "TR909" stays in one
    piece but "TR909Clap" splits after it. A number after a small letter
    breaks the same way ("Break170" -> "Break" "170").
    """
    words = []
    current = ""
    previous = ""
    for ch in text:
        if current and ((ch.isupper() and (previous.islower() or previous.isdigit()))
                        or (ch.isdigit() and previous.islower())):
            words.append(current)
            current = ""
        current += ch
        previous = ch
        if ch in _BREAKS:
            words.append(current)
            current = ""
    if current:
        words.append(current)
    return words or [""]


def split_number(text):
    """Sample names start with their number in the preset ("01Kick"). Returns
    (number, rest) so the number can go in the corner of the tile instead of
    eating into the name."""
    if len(text) > 2 and text[:2].isdigit():
        return text[:2], text[2:].lstrip(_BREAKS) or text[2:]
    return "", text


def wrap(text, font, max_width, max_lines):
    """Break text into at most max_lines lines fitting max_width, or None if
    it does not go at this font size."""
    lines = []
    line = ""
    for word in split_name(text):
        candidate = line + word
        if line and font.size(candidate.rstrip())[0] > max_width:
            lines.append(line.rstrip())
            line = word
        else:
            line = candidate
        if len(lines) > max_lines:
            return None
    if line:
        lines.append(line.rstrip())
    if not lines or len(lines) > max_lines:
        return None
    for one in lines:
        # a single word wider than the tile cannot be broken at a separator
        if font.size(one)[0] > max_width:
            return None
    return lines


# Tried from big to small - the first size the name fits in wins.
_SIZES = (64, 58, 52, 46, 42, 38, 34, 30, 27, 24, 21, 18, 16)


def wrap_chars(text, font, max_width, max_lines):
    """Break anywhere. For names without a separator in them, which would
    otherwise have to be shrunk down to nothing."""
    lines = []
    line = ""
    for ch in text:
        if line and font.size(line + ch)[0] > max_width:
            lines.append(line)
            line = ch
            if len(lines) >= max_lines:
                return None
        else:
            line += ch
    if line:
        lines.append(line)
    return lines or None


def fit_text(text, max_width, max_height, max_lines=3, bold=True):
    """Biggest font the text fits into. Returns (font, lines)."""
    for breaker in (wrap, wrap_chars):
        for size in _SIZES:
            font = get_font(size, bold)
            lines = breaker(text, font, max_width, max_lines)
            if lines and font.get_linesize() * len(lines) <= max_height:
                return font, lines
    # last resort: cut the name off rather than let it spill over the tile
    font = get_font(_SIZES[-1], bold)
    cut = text
    while len(cut) > 1 and font.size(cut)[0] > max_width:
        cut = cut[:-1]
    return font, [cut]


## BACKGROUND ##

class Background:
    """The red/green line fan, pre-rendered into a few frames that loop.

    Animating it by drawing the lines every frame would cost hundreds of line
    calls per frame on the Pi; blitting one finished surface costs one memcpy.
    The frames are built once at startup - config.UI_ANIM_FPS = 0 turns the
    movement (and the extra memory) off completely.
    """

    SPACING = 25

    def __init__(self):
        self.width = SCREEN_W
        self.height = SCREEN_H
        self.fps = max(0.0, float(config.UI_ANIM_FPS))
        count = config.UI_ANIM_FRAMES if self.fps > 0 else 1
        count = max(1, int(count))
        self.frames = [self._render(f / float(count)) for f in range(count)]
        self.index = 0

    def _render(self, phase):
        """One frame of the pattern, ready to blit."""
        surface = pygame.Surface((self.width, self.height))
        self.draw_fan(surface, phase)
        try:
            return surface.convert()
        except pygame.error:    # no display yet
            return surface

    def draw_fan(self, surface, phase, wave_phase=None, gain=1.0):
        """Draw the pattern straight onto a surface.

        `phase` (0..1) shifts the lines by one spacing, so phase 1 joins phase
        0 again. `wave_phase` moves the bright band along the fan and defaults
        to `phase`, which is what keeps a pre-rendered loop seamless; the
        splash screen drives the two at different speeds (and dims with
        `gain`) so nothing about it repeats on the second.
        """
        if wave_phase is None:
            wave_phase = phase
        surface.fill(Color('black'))
        step = self.SPACING
        drift = phase * step

        # Same fan as before, but each line gets its own shade and the
        # brightness travels along it, so the pattern breathes instead of
        # just sliding.
        for k in range(-1, self.width // step + 2):
            i = k * step + drift
            t = i / float(self.width)

            if 0 <= i <= self.height:
                wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * (t * 2.5 - wave_phase))
                green = int(255 * gain * (1.0 - 0.45 * t) * (0.12 + 0.88 * wave))
                green = max(0, min(255, green))
                pygame.draw.line(surface, (0, green, int(green * 0.22)),
                                 (0, i), (i, self.height), 1)

            if 0 <= i <= self.width:
                wave = 0.5 + 0.5 * math.sin(2.0 * math.pi * (t * 2.5 + wave_phase))
                red = int(255 * gain * (0.55 + 0.45 * t) * (0.12 + 0.88 * wave))
                red = max(0, min(255, red))
                pygame.draw.line(surface, (red, 0, int(red * 0.15)),
                                 (i, 0), (self.width, i), 1)

        # thin frame, in the accent colour
        pygame.draw.rect(surface, GB, (0, 0, self.width, self.height), 3)

    def tick(self, now):
        """Advance the animation. Returns True when the frame changed."""
        if self.fps <= 0 or len(self.frames) < 2:
            return False
        index = int(now * self.fps) % len(self.frames)
        if index == self.index:
            return False
        self.index = index
        return True

    def draw(self, screen):
        screen.blit(self.frames[self.index], (0, 0))

    # How fast the live pattern moves on the splash screen: the lines drift
    # one spacing every three seconds, the bright band runs along them more
    # than twice as fast, and the whole thing swells slowly. The three speeds
    # do not divide into each other, so it never repeats on the beat.
    DRIFT_PER_SECOND = 0.33
    WAVE_PER_SECOND = 0.72
    SWELL_PER_SECOND = 0.11

    def draw_live(self, screen, now):
        """Keep evolving instead of looping - for the splash screen."""
        if self.fps <= 0:
            self.draw(screen)
            return
        gain = 0.72 + 0.28 * (0.5 + 0.5 * math.sin(2.0 * math.pi
                                                   * now * self.SWELL_PER_SECOND))
        self.draw_fan(screen,
                      (now * self.DRIFT_PER_SECOND) % 1.0,
                      (now * self.WAVE_PER_SECOND) % 1.0,
                      gain)


## LOGO ##

# The old full screen frame graphic holds both parts of the logo: the face
# on its own, and the "Calmy Jane's Samplemania" wordmark next to it.
ICON_BOX = (492, 58, 604, 152)
WORD_BOX = (33, 77, 468, 135)


def logo_part(box, height):
    """Cut one part of the logo out of the frame graphic, scaled to height."""
    x0, y0, x1, y1 = box
    frame = load_image(asset('background.png'))
    part = frame.subsurface(pygame.Rect(x0, y0, x1 - x0, y1 - y0)).copy()
    scale = height / float(y1 - y0)
    part = pygame.transform.smoothscale(part, (int((x1 - x0) * scale), height))
    try:
        return part.convert_alpha()
    except pygame.error:        # no display yet
        return part


## HEADER ##

class Header:
    """Logo, current screen and preset, in one shallow strip."""

    # Only the face, not the wordmark - the name belongs on the splash
    # screen, the strip is for what is going on right now.
    LOGO_H = 40

    # The PiBoy draws its own HUD over both top corners, so the strip keeps
    # clear of them: everything on the left starts a good fifth of the screen
    # in, everything on the right ends a twentieth of it early.
    LEFT_INSET = (SCREEN_W * 24) // 100
    RIGHT_INSET = SCREEN_W // 20

    def __init__(self):
        self.bar = pygame.Surface((SCREEN_W, HEADER_H))
        self.bar.fill((8, 10, 12))
        self.bar.set_alpha(215)
        try:
            self.bar = self.bar.convert()
            self.bar.set_alpha(215)
        except pygame.error:
            pass

        self.logo = logo_part(ICON_BOX, self.LOGO_H)
        self.logo_pos = (self.LEFT_INSET, (HEADER_H - self.LOGO_H) // 2)

        self.tag = None
        self.title = ""
        self.badge = None
        self._tag_img = None
        self._title_img = None
        self._badge_img = None
        self._title_cap = -1
        self._title_text = None
        self.set_title("", "1/1")       # builds the badge the layout needs
        self.set_tag("PLAY")

    def set_tag(self, tag):
        """The chip next to the logo: which screen you are on."""
        if tag != self.tag:
            self.tag = tag
            self._tag_img = get_font(22, True).render(tag, True, GB_TEXT)
        self._render_title()

    def set_title(self, title, badge):
        """Right hand side: what is loaded (preset, sample) and a short
        counter after it (page, root note)."""
        if badge != self.badge:
            self.badge = badge
            self._badge_img = get_font(26, True).render(badge, True, MARK)
        self.title = title
        self._render_title()

    def _render_title(self):
        """The title gets whatever room the chip and the counter leave, and
        is cut to fit - a long preset name must never run into them."""
        if self._tag_img is None or self._badge_img is None:
            return                  # still being built, see __init__
        chip_end = (self.logo_pos[0] + self.logo.get_width() + 14
                    + self._tag_img.get_width() + 16)
        cap = (SCREEN_W - 14 - self.RIGHT_INSET - self._badge_img.get_width()
               - 14 - chip_end - 12)
        cap = max(80, cap)
        if (cap == self._title_cap and self._title_img is not None
                and self.title == self._title_text):
            return
        self._title_cap = cap
        self._title_text = self.title
        font = get_font(30, True)
        text = self.title.upper()
        while len(text) > 1 and font.size(text)[0] > cap:
            text = text[:-1]
        self._title_img = font.render(text, True, (235, 240, 235))

    def draw(self, screen):
        screen.blit(self.bar, (0, 0))
        screen.blit(self.logo, self.logo_pos)

        # screen tag, as a chip right of the logo
        w = self._tag_img.get_width() + 16
        x = self.logo_pos[0] + self.logo.get_width() + 14
        pygame.draw.rect(screen, GB, (x, 13, w, 26))
        screen.blit(self._tag_img, (x + 8, 17))

        # title right aligned, its counter after it
        px = SCREEN_W - 14 - self.RIGHT_INSET - self._badge_img.get_width()
        screen.blit(self._badge_img, (px, 15))
        screen.blit(self._title_img, (px - 14 - self._title_img.get_width(), 12))

        pygame.draw.line(screen, GB, (3, HEADER_H), (SCREEN_W - 4, HEADER_H), 2)


## SAMPLE GRID ##

_PANELS = {}        # (size, colours) -> empty panel, see SampleTile._panel


class SampleTile:
    """One sample slot: a chamfered panel with the name as big as it fits.

    Both looks (idle and lit) are rendered when the name changes, so a button
    press only swaps which surface is blitted - no font rendering in the
    middle of a performance.
    """

    CHAMFER = 14
    PAD = 12

    # The panels are slightly see-through, so the moving lines stay visible
    # underneath. The tiles are drawn from a per-pixel alpha surface anyway
    # (the chamfered corners need it), so this costs nothing extra.
    IDLE_TOP = (34, 22, 30, 224)
    IDLE_BOTTOM = (13, 9, 12, 224)
    IDLE_BORDER = GB
    IDLE_TEXT = (238, 228, 234)

    HOT_TOP = (198, 62, 116, 250)
    HOT_BOTTOM = (86, 16, 50, 250)
    HOT_BORDER = (255, 214, 232)
    HOT_TEXT = (255, 240, 246)

    EMPTY_TOP = (18, 18, 20, 190)
    EMPTY_BOTTOM = (9, 9, 10, 190)
    EMPTY_BORDER = (54, 54, 58)
    EMPTY_TEXT = (96, 96, 100)

    def __init__(self, rect, letter, row=False):
        self.rect = rect
        self.letter = letter
        self.row = row      # a wide list row instead of a box
        self.text = None
        self.name = ""
        self.number = ""
        self.sub = ""
        self.empty = True
        self.hot = False
        self.playing = False
        self.loading = False
        self.idle_img = None
        self.hot_img = None
        self.set_text("")

    ## CONTENT (setters return True when something actually changed) ##

    def set_text(self, text, sub=""):
        if text == self.text and sub == self.sub:
            return False
        self.text = text
        self.sub = sub
        self.number, self.name = split_number(text)
        self.empty = text in ("", "<EMPTY>", "-")
        self.idle_img = self._render(False)
        self.hot_img = self._render(True)
        return True

    def set_hot(self, hot):
        if hot == self.hot:
            return False
        self.hot = hot
        return True

    def set_playing(self, playing):
        if playing == self.playing:
            return False
        self.playing = playing
        return True

    def set_loading(self, loading):
        if loading == self.loading:
            return False
        self.loading = loading
        return True

    ## RENDERING ##

    def _colors(self, hot):
        if self.empty:
            return self.EMPTY_TOP, self.EMPTY_BOTTOM, self.EMPTY_BORDER, self.EMPTY_TEXT
        if hot:
            return self.HOT_TOP, self.HOT_BOTTOM, self.HOT_BORDER, self.HOT_TEXT
        return self.IDLE_TOP, self.IDLE_BOTTOM, self.IDLE_BORDER, self.IDLE_TEXT

    def _outline(self, w, h):
        c = self.CHAMFER if not self.row else self.ROW_CHAMFER
        return [(c, 0), (w - c, 0), (w - 1, c), (w - 1, h - c),
                (w - c, h - 1), (c, h - 1), (0, h - c), (0, c)]

    ROW_CHAMFER = 10

    def _panel(self, w, h, top, bottom, border):
        """The empty panel. All tiles are the same size and there are only
        three looks, so the row by row gradient is drawn three times for the
        whole app and copied from there - a page change is then six copies
        and the names, not twelve gradients."""
        key = (w, h, top, bottom, border)
        panel = _PANELS.get(key)
        if panel is not None:
            return panel
        panel = pygame.Surface((w, h), pygame.SRCALPHA)

        # Each row is pulled in at the ends near the corners: that is where
        # the chamfer comes from, so nothing has to be masked out afterwards
        # and the corners stay transparent.
        c = self.CHAMFER if not self.row else self.ROW_CHAMFER
        for y in range(h):
            f = y / float(max(1, h - 1))
            color = tuple(int(top[i] + (bottom[i] - top[i]) * f)
                          for i in range(len(top)))
            inset = max(0, c - y, c - (h - 1 - y))
            pygame.draw.line(panel, color, (inset, y), (w - 1 - inset, y))

        pygame.draw.lines(panel, border, True, self._outline(w, h), 3)
        try:
            panel = panel.convert_alpha()
        except pygame.error:    # no display yet
            pass
        _PANELS[key] = panel
        return panel

    def _render(self, hot):
        w, h = self.rect.width, self.rect.height
        top, bottom, border, textcol = self._colors(hot)
        surface = self._panel(w, h, top, bottom, border).copy()
        if self.row:
            return self._render_row(surface, w, h, textcol)

        # button letter top left, number in the preset top right
        letter = get_font(26, True).render(self.letter, True, MARK)
        surface.blit(letter, (self.PAD, 5))
        if self.number:
            number = get_font(26, True).render(self.number, True, MARK)
            surface.blit(number, (w - self.PAD - number.get_width(), 5))

        name = self.name if not self.empty else "-"
        avail_w = w - 2 * self.PAD
        avail_h = h - 34 - (20 if self.sub else 0)
        font, lines = fit_text(name, avail_w, avail_h)
        line_h = font.get_linesize()
        y = 28 + (avail_h - line_h * len(lines)) // 2
        for line in lines:
            img = font.render(line, True, textcol)
            surface.blit(img, ((w - img.get_width()) // 2, y))
            y += line_h

        if self.sub:
            img = get_font(24, True).render(self.sub, True, textcol)
            surface.blit(img, ((w - img.get_width()) // 2, h - 28))

        try:
            return surface.convert_alpha()
        except pygame.error:    # no display yet
            return surface

    def _render_row(self, surface, w, h, textcol):
        """List style: button letter and number on the left, then the name on
        one line, as tall as the row allows."""
        font = get_font(30, True)
        letter = font.render(self.letter, True, MARK)
        surface.blit(letter, (self.PAD, (h - letter.get_height()) // 2))
        if self.number:
            number = font.render(self.number, True, MARK)
            surface.blit(number, (self.PAD + 26, (h - number.get_height()) // 2))

        left = self.PAD + 26 + 38
        right = self.PAD + (46 if self.sub else 0)
        name = self.name if not self.empty else "-"
        font, lines = fit_text(name, w - left - right, h - 8, max_lines=1)
        img = font.render(lines[0], True, textcol)
        surface.blit(img, (left, (h - img.get_height()) // 2))

        if self.sub:
            img = get_font(26, True).render(self.sub, True, textcol)
            surface.blit(img, (w - self.PAD - img.get_width(),
                               (h - img.get_height()) // 2))
        try:
            return surface.convert_alpha()
        except pygame.error:    # no display yet
            return surface

    ## DRAW ##

    def draw(self, screen, pulse):
        screen.blit(self.hot_img if (self.hot or self.playing) else self.idle_img,
                    self.rect)
        r = self.rect
        if self.playing and not self.hot:
            # still sounding after the finger left: a breathing outline
            shade = int(110 + 145 * pulse)
            pygame.draw.lines(screen, (255, shade, min(255, shade + 40)), True,
                              [(r.x + p[0], r.y + p[1])
                               for p in self._outline(r.width, r.height)], 3)
        if self.loading:
            # not in RAM yet - the loader thread is still reading it
            y = r.centery if self.row else r.y + 14
            pygame.draw.circle(screen, (230, 170, 40),
                               (r.right - self.PAD - 4, y), 5)


BOXES = "boxes"
LIST = "list"


class SampleGrid:
    """The six sample slots, in one of two styles (config.UI_STYLE, and the
    menu switches between them live).

    BOXES lays them out like the six buttons of the pad: top row Z Y X, bottom
    row C B A, the columns stepping up towards the right the way the buttons
    do - so the tile you read sits where your thumb is. LIST stacks them as
    six wide rows, the way the app looked before, which reads better for long
    names.

    Either way a pressed button lights its slot and one that is still sounding
    keeps a breathing outline. That replaces the old button and d-pad
    pictures, which are only drawn now when config.SHOW_DEBUG_PADS is on.
    """

    COLS = 3
    ROWS = 2
    GAP = 14
    ROW_GAP = 7
    STAGGER = 8         # per column, the right hand side sits higher
    LETTERS = ("Z", "Y", "X", "C", "B", "A")

    def __init__(self, rect, style=BOXES):
        self.rect = pygame.Rect(rect)
        self.pulse = 0.0
        self.style = None
        self.tiles = []
        # what is in the slots, kept so a style change can rebuild the tiles
        # without the modes having to fill them again
        self._texts = [("", "")] * 6
        self._states = [(False, False, False)] * 6   # hot, playing, loading
        self.set_style(style)

    ## LAYOUT ##

    def set_style(self, style):
        """Switch between BOXES and LIST, keeping what is in the slots."""
        if style == self.style:
            return False
        self.style = style
        self.tiles = self._rows() if style == LIST else self._boxes()
        for i, tile in enumerate(self.tiles):
            tile.set_text(*self._texts[i])
            hot, playing, loading = self._states[i]
            tile.set_hot(hot)
            tile.set_playing(playing)
            tile.set_loading(loading)
        return True

    def _boxes(self):
        tile_w = (self.rect.width - (self.COLS - 1) * self.GAP) // self.COLS
        tile_h = (self.rect.height - (self.ROWS - 1) * self.GAP
                  - (self.COLS - 1) * self.STAGGER) // self.ROWS
        tiles = []
        for index in range(self.COLS * self.ROWS):
            col = index % self.COLS
            row = index // self.COLS
            x = self.rect.x + col * (tile_w + self.GAP)
            y = (self.rect.y + (self.COLS - 1 - col) * self.STAGGER
                 + row * (tile_h + self.GAP))
            tiles.append(SampleTile(pygame.Rect(x, y, tile_w, tile_h),
                                    self.LETTERS[index]))
        return tiles

    def _rows(self):
        row_h = (self.rect.height - 5 * self.ROW_GAP) // 6
        return [SampleTile(pygame.Rect(self.rect.x,
                                       self.rect.y + i * (row_h + self.ROW_GAP),
                                       self.rect.width, row_h),
                           self.LETTERS[i], row=True)
                for i in range(6)]

    ## CONTENT (all return True when something actually changed) ##

    def set_strings(self, strings, subs=None):
        changed = False
        for i, tile in enumerate(self.tiles):
            text = strings[i] if i < len(strings) else ""
            sub = subs[i] if subs and i < len(subs) else ""
            self._texts[i] = (text, sub)
            if tile.set_text(text, sub):
                changed = True
        return changed

    def _set_state(self, index, slot, value):
        state = list(self._states[index])
        state[slot] = value
        self._states[index] = tuple(state)

    def highlight(self, index, high):
        self._set_state(index, 0, high)
        return self.tiles[index].set_hot(high)

    def set_playing(self, index, playing):
        self._set_state(index, 1, playing)
        return self.tiles[index].set_playing(playing)

    def set_loading(self, index, loading):
        self._set_state(index, 2, loading)
        return self.tiles[index].set_loading(loading)

    def clear(self):
        for i, tile in enumerate(self.tiles):
            self._states[i] = (False, False, False)
            tile.set_hot(False)
            tile.set_playing(False)
            tile.set_loading(False)

    def tick(self, now):
        self.pulse = 0.5 + 0.5 * math.sin(now * 6.0)

    def draw(self, screen):
        for tile in self.tiles:
            tile.draw(screen, self.pulse)


class Splash:
    """The title screen: the face, the wordmark under it, and the line
    pattern drawn live so it keeps evolving instead of looping."""

    ICON_H = 150
    WORD_W = 500

    def __init__(self):
        self.icon = logo_part(ICON_BOX, self.ICON_H)
        x0, y0, x1, y1 = WORD_BOX           # scale the wordmark by its width
        self.word = logo_part(WORD_BOX,
                              max(1, int(self.WORD_W * (y1 - y0) / float(x1 - x0))))
        self.hint = get_font(26, True).render("PRESS ANY BUTTON", True, GB_TEXT)

        total = self.icon.get_height() + 24 + self.word.get_height()
        top = (SCREEN_H - total) // 2 - 20
        self.icon_pos = ((SCREEN_W - self.icon.get_width()) // 2, top)
        self.word_pos = ((SCREEN_W - self.word.get_width()) // 2,
                         top + self.icon.get_height() + 24)

    def draw(self, screen, background, now):
        background.draw_live(screen, now)
        screen.blit(self.icon, self.icon_pos)
        screen.blit(self.word, self.word_pos)
        # the hint fades in and out so it reads as "waiting for you"
        if math.sin(now * 3.0) > -0.3:
            x = (SCREEN_W - self.hint.get_width()) // 2
            pygame.draw.rect(screen, (8, 10, 12),
                             (x - 10, SCREEN_H - 62, self.hint.get_width() + 20,
                              self.hint.get_height() + 8))
            screen.blit(self.hint, (x, SCREEN_H - 58))


class Panel:
    """A chamfered, slightly see-through dark panel - the same shape as a
    sample tile, for screens that show a list instead of six names."""

    CHAMFER = 16

    def __init__(self, rect, border=GB, fill=(22, 15, 20, 224)):
        self.rect = pygame.Rect(rect)
        w, h = self.rect.width, self.rect.height
        surface = pygame.Surface((w, h), pygame.SRCALPHA)
        c = self.CHAMFER
        for y in range(h):
            inset = max(0, c - y, c - (h - 1 - y))
            pygame.draw.line(surface, fill, (inset, y), (w - 1 - inset, y))
        pygame.draw.lines(surface, border, True,
                          [(c, 0), (w - c, 0), (w - 1, c), (w - 1, h - c),
                           (w - c, h - 1), (c, h - 1), (0, h - c), (0, c)], 3)
        try:
            surface = surface.convert_alpha()
        except pygame.error:    # no display yet
            pass
        self.image = surface

    def draw(self, screen):
        screen.blit(self.image, self.rect)


## DEBUG OVERLAY (config.SHOW_DEBUG_PADS) ##

class Button(pygame.sprite.Sprite):
    def __init__(self, position, on_img, off_img):
        """on_img / off_img are ready surfaces - the row scales them once and
        hands the same two to all six buttons."""
        self.pressed = False
        self.position = position
        self.off_image = off_img
        self.on_image = on_img
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
    def __init__(self, position, size=24):
        self.position = position
        pygame.sprite.Group.__init__(self)
        self.spritelist = []
        on = pygame.transform.smoothscale(load_image(asset("button_on.png")), (size, size))
        off = pygame.transform.smoothscale(load_image(asset("button_off.png")), (size, size))
        step = size + 3
        for i in range(3):
            for j in range(2):
                btn = Button((i * step + self.position[0],
                              j * step + self.position[1] - i * (size // 3)), on, off)
                self.add(btn)
                self.spritelist.append(btn)

    def set_button(self, index, pressed):
        self.spritelist[index].set_state(pressed)


class Dpad():
    IMAGES = (('bg', 'cross_bg.png'),
              ('up_on', 'cross_up_on.png'), ('up_off', 'cross_up_off.png'),
              ('down_on', 'cross_down_on.png'), ('down_off', 'cross_down_off.png'),
              ('left_on', 'cross_left_on.png'), ('left_off', 'cross_left_off.png'),
              ('right_on', 'cross_right_on.png'), ('right_off', 'cross_right_off.png'))

    def __init__(self, pos, size=56, *args, **kwargs):
        self.pos = pos
        for name, filename in self.IMAGES:
            image = pygame.transform.smoothscale(load_image(asset(filename)), (size, size))
            setattr(self, name + '_img', image)
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
        screen.blit(self.bg_img, self.rect)
        screen.blit(self.up_on_img if self.up else self.up_off_img, self.rect)
        screen.blit(self.down_on_img if self.down else self.down_off_img, self.rect)
        screen.blit(self.left_on_img if self.left else self.left_off_img, self.rect)
        screen.blit(self.right_on_img if self.right else self.right_off_img, self.rect)


class DebugPads:
    """The old button and d-pad pictures, shrunk into a corner. Off by
    default - handy when a button on the device seems not to arrive."""

    def __init__(self, pos=(8, 400)):
        self.dpad = Dpad(pos)
        self.buttonrow = ButtonRow((pos[0] + 66, pos[1] + 14))

    def draw(self, screen, app):
        self.dpad.set_values(app.input.up, app.input.down,
                             app.input.left, app.input.right)
        self.dpad.draw(screen)
        self.buttonrow.draw(screen)


class Text:
    """A string rendered once, and re-rendered only when it changes."""

    def __init__(self, text, pos, fontsize, color, bgcolor, **options):
        self.text = text
        self.pos = pos
        self.fontsize = fontsize
        self.color = color
        self.bgcolor = bgcolor
        self.padding = options.get('padding', 1)   # bg margin around the text
        self.bold = options.get('bold', False)
        self.font = get_font(fontsize, self.bold)
        self.render()

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
        if self.bgcolor is not None:
            pygame.draw.rect(screen, self.bgcolor,
                             self.rect.inflate(self.padding * 2, self.padding * 2))
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
            pygame.draw.rect(screen, (255, 255, 255),
                             (x + 2 + min(hold, w - 6), y + 2, 2, h - 4))

        # clip led
        led = (255, 40, 40) if self.clipped else (60, 20, 20)
        pygame.draw.rect(screen, led, (x + w + 10, y, h, h))
        pygame.draw.rect(screen, (90, 90, 90), (x + w + 10, y, h, h), 2)


class ConfirmDialog:
    """Modal yes/no box drawn over whatever mode is active."""

    SIZE = (520, 180)

    def __init__(self, message="", detail=""):
        w, h = self.SIZE
        self.rect = pygame.Rect((SCREEN_W - w) // 2, (SCREEN_H - h) // 2, w, h)
        x, y = self.rect.x, self.rect.y

        self.overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        self.overlay.set_alpha(190)
        self.overlay.fill((0, 0, 0))

        self.title = Text(message, (x + 24, y + 22), 38, Color('white'), None, bold=True)
        self.detail = Text(detail, (x + 24, y + 68), 26, (200, 200, 200), None)
        self.hint = Text("A = YES     B = NO", (x + 24, y + 122), 30,
                         (255, 210, 80), None, bold=True)

    def draw(self, screen):
        screen.blit(self.overlay, (0, 0))
        pygame.draw.rect(screen, (25, 25, 30), self.rect)
        pygame.draw.rect(screen, (230, 60, 60), self.rect, 3)
        self.title.draw(screen)
        if self.detail.text:
            self.detail.draw(screen)
        self.hint.draw(screen)
