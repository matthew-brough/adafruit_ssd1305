# SPDX-FileCopyrightText: 2026 Your Name
# SPDX-License-Identifier: MIT
"""
CPython SSD1305 driver using smbus3 and PIL, API compatible with Adafruit CircuitPython SSD1305.
"""
import time
from PIL import Image, ImageDraw, ImageFont
import smbus3
import RPi.GPIO as GPIO

SSD1305_I2C_ADDR = 0x3C
RESET_PIN = 0x04

# SSD1305 command constants
SET_CONTRAST = 0x81
SET_ENTIRE_ON = 0xA4
SET_NORM_INV = 0xA6
SET_DISP = 0xAE
SET_MEM_ADDR = 0x20
SET_COL_ADDR = 0x21
SET_PAGE_ADDR = 0x22
SET_DISP_START_LINE = 0x40
SET_LUT = 0x91
SET_SEG_REMAP = 0xA0
SET_MUX_RATIO = 0xA8
SET_MASTER_CONFIG = 0xAD
SET_COM_OUT_DIR = 0xC0
SET_COMSCAN_DEC = 0xC8
SET_DISP_OFFSET = 0xD3
SET_COM_PIN_CFG = 0xDA
SET_DISP_CLK_DIV = 0xD5
SET_AREA_COLOR = 0xD8
SET_PRECHARGE = 0xD9
SET_VCOM_DESEL = 0xDB
SET_CHARGE_PUMP = 0x8D


class SSD1305:
    def __init__(
        self, width, height, i2c_bus=1, addr=SSD1305_I2C_ADDR, col=4, external_vcc=False, reset_pin: int | None = None
    ):
        self.width = width
        self.height = height
        self.addr = addr
        self.external_vcc = external_vcc
        self.bus = smbus3.SMBus(i2c_bus)
        self.pages = self.height // 8
        self._image = Image.new("1", (self.width, self.height))
        # Buffer with extra byte at start for I2C data/command byte (0x40)
        self.buffer = bytearray(((self.height // 8) * self.width) + 1)
        self.buffer[0] = 0x40  # Co=0, D/C=1 for data
        self._column_offset = col if col is not None else 4
        self.reset_pin = reset_pin

        if self.reset_pin:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.reset_pin, GPIO.OUT)

        self.poweron()
        self.init_display()

    def gpio_write(self, pin, value):
        GPIO.output(pin, value)

    def poweron(self):
        """Reset device and turn on the display."""
        if self.reset_pin:
            self.gpio_write(self.reset_pin, 1)
            time.sleep(0.001)
            self.gpio_write(self.reset_pin, 0)
            time.sleep(0.010)
            self.gpio_write(self.reset_pin, 1)
            time.sleep(0.010)
        self.write_cmd(SET_DISP | 0x01)

    def write_cmd(self, cmd):
        self.bus.write_i2c_block_data(self.addr, 0x80, [cmd])

    def write_framebuf(self):
        """Blast out the frame buffer using I2C transactions."""
        # The first byte of self.buffer is 0x40 (data mode)
        # Send in chunks due to I2C buffer limitations (32 bytes max per transaction)
        # Skip the 0x40 prefix byte and send data with 0x40 control byte
        data = memoryview(self.buffer)[1:]  # Skip the leading 0x40
        chunk_size = 31  # Leave room for control byte
        for i in range(0, len(data), chunk_size):
            chunk = list(data[i : i + chunk_size])
            self.bus.write_i2c_block_data(self.addr, 0x40, chunk)

    def init_display(self):
        for cmd in (
            SET_DISP | 0x00,
            SET_DISP_CLK_DIV,
            0x80,
            SET_SEG_REMAP | 0x01,
            SET_MUX_RATIO,
            self.height - 1,
            SET_DISP_OFFSET,
            0x00,
            SET_MASTER_CONFIG,
            0x8E,
            SET_AREA_COLOR,
            0x05,
            SET_MEM_ADDR,
            0x00,
            SET_DISP_START_LINE | 0x00,
            0x2E,
            SET_COMSCAN_DEC,
            SET_COM_PIN_CFG,
            0x12,
            SET_LUT,
            0x3F,
            0x3F,
            0x3F,
            0x3F,
            SET_CONTRAST,
            0xFF,
            SET_PRECHARGE,
            0xD2,
            SET_VCOM_DESEL,
            0x34,
            SET_NORM_INV,
            SET_ENTIRE_ON,
            SET_CHARGE_PUMP,
            0x10 if self.external_vcc else 0x14,
            SET_DISP | 0x01,
        ):
            self.write_cmd(cmd)
        self.fill(0)
        self.show()

    def fill(self, color):
        """Fill the display with a color (0=black, 1=white)."""
        fill_byte = 0xFF if color else 0x00
        # Skip first byte (0x40 control byte)
        for i in range(1, len(self.buffer)):
            self.buffer[i] = fill_byte
        self._image.paste(color, (0, 0, self.width, self.height))

    def pixel(self, x, y, color):
        """Set a pixel at (x, y) to the given color."""
        if 0 <= x < self.width and 0 <= y < self.height:
            page = y // 8
            shift = y % 8
            # +1 to skip the 0x40 control byte at buffer[0]
            idx = x + page * self.width + 1
            if color:
                self.buffer[idx] |= 1 << shift
            else:
                self.buffer[idx] &= ~(1 << shift)
            self._image.putpixel((x, y), color)

    def show(self):
        """Update the display."""
        self._image_to_buffer()
        # Set column address with offset
        xpos0 = 0
        xpos1 = self.width - 1
        if self.width == 64:
            # displays with width of 64 pixels are shifted by 32
            xpos0 += 32
            xpos1 += 32
        self.write_cmd(SET_COL_ADDR)
        self.write_cmd(xpos0 + self._column_offset)
        self.write_cmd(xpos1 + self._column_offset)
        self.write_cmd(SET_PAGE_ADDR)
        self.write_cmd(0)
        self.write_cmd(self.pages - 1)
        self.write_framebuf()

    def _image_to_buffer(self):
        """Convert PIL image to buffer."""
        pixels = self._image.load()
        if pixels is None:
            return
        for x in range(self.width):
            for page in range(self.pages):
                byte = 0
                for bit in range(8):
                    y = page * 8 + bit
                    if y >= self.height:
                        continue
                    if pixels[x, y]:
                        byte |= 1 << bit
                # +1 to skip the 0x40 control byte at buffer[0]
                self.buffer[x + page * self.width + 1] = byte

    @property
    def image(self):
        """Return the PIL image for drawing. Use show() to update display."""
        return self._image

    @image.setter
    def image(self, img):
        """Set a new PIL image."""
        self._image = img

    def contrast(self, contrast):
        self.write_cmd(SET_CONTRAST)
        self.write_cmd(contrast)

    def invert(self, invert):
        self.write_cmd(SET_NORM_INV | (invert & 1))

    def poweroff(self):
        self.write_cmd(SET_DISP | 0x00)


if __name__ == "__main__":
    display = SSD1305(width=128, height=32, i2c_bus=1, col=4)
    draw = ImageDraw.Draw(display.image)
    font = ImageFont.load_default()
    draw.text((0, -2), "Hello, SSD1305!", font=font, fill=1)
    draw.text((0, 6), "This is a test.", font=font, fill=1)
    draw.text((0, 14), "Drawing text...", font=font, fill=1)
    draw.text((0, 22), "Goodbye!", font=font, fill=1)
    display.show()
    exit()
    # Draw a pattern on the display
    for x in range(display.width):
        for y in range(display.height):
            if (x // 8 + y // 8) % 2 == 0:
                display.image.putpixel((x, y), 1)
            else:
                display.image.putpixel((x, y), 0)

    # Update the framebuffer
    display.show()
