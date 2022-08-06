import os
import pygame
from pygame import draw
from pygame.locals import *

class Button(pygame.sprite.Sprite):
    def __init__(self, position, on_img, off_img):
        self.pressed = False
        self.position = position
        self.off_image = pygame.image.load(off_img)
        self.on_image = pygame.image.load(on_img)
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
                btn = Button((i*50 + self.position[0], j*50 + self.position[1] - i*15), "/home/pi/RetroPie/roms/python/button_on.png", "/home/pi/RetroPie/roms/python/button_off.png")
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
            txt.render()
            txt.draw(screen)

    def set_strings(self, strings):
        for i, text in enumerate(self.texts):
            text.text = strings[i]

    def highlight(self, index, high):
        self.texts[index].bgcolor = (200,20,20) if high else (250, 20, 20)

class Background:
    def __init__(self):
        self.height = 480
        self.width = 640
        self.size = 25
        self.image = pygame.image.load('/home/pi/RetroPie/roms/python/background.png')

    def draw(self, screen):
        screen.fill(Color('black'))
        for i in range ( 0, self.width, self.size ):
            pygame.draw.line ( screen, ( 0, 250-i/25, 0 ), ( 0, i ), ( i, self.height ), 1 )
            pygame.draw.line ( screen, ( 200+i/15, 0, 0 ), ( i, 0 ), ( self.width, i ), 1 )
            #pygame.draw.line ( screen, ( 200-i/15, 0, 0 ), ( self.width - i, 0 ), ( 0, i ), 1 )
            #pygame.draw.line ( screen, ( 0, 250-i/25, 0 ), ( i, self.height ), ( self.width, self.height - i ), 1 )
        screen.blit(self.image, self.image.get_rect())

class Dpad():
    def __init__(self,pos, *args, **kwargs):
        self.pos = pos
        self.bg_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_bg.png')
        self.up_on_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_up_on.png')
        self.up_off_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_up_off.png')
        self.down_on_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_down_on.png')
        self.down_off_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_down_off.png')
        self.left_on_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_left_on.png')
        self.left_off_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_left_off.png')
        self.right_on_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_right_on.png')
        self.right_off_img = pygame.image.load('/home/pi/RetroPie/roms/python/cross_right_off.png')
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

    def draw(self, screen):
        """Draw the text image to the screen."""
        if self.bgcolor != None:
            pygame.draw.rect(screen, self.bgcolor, self.rect.inflate(2,2))
        screen.blit(self.img, self.rect)