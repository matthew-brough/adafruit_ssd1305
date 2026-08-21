from __future__ import annotations

import pathlib
import time
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont
from smbus3 import SMBus

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    GPIO = None

try:
    from . import constants
    from .bitmap_font import BitmapFont, list_fonts
except ImportError:
    import constants
    from bitmap_font import BitmapFont, list_fonts

if TYPE_CHECKING:
    from types import TracebackType
    from typing import Self, Literal

FONT_FOLDER = pathlib.Path(__file__).resolve().parent / "fonts"


class SSD1305:
    _bus: SMBus
    _image: Image.Image
    _buffer: bytearray
    _column_offset: int
    _page_offset: int

    def __init__(
        self,
        width: int,
        height: int,
        i2c_bus: int = 1,
        i2c_address: int = constants.SSD1305_I2C_ADDRESS,
        external_vcc: bool = False,
        reset_pin: int | None = None,
        font_path: pathlib.Path | None = None,
        font_size: int = 8,
        font_format: constants.FontType = constants.FontType.TTF,
    ) -> None:
        self._width = width
        self._height = height
        self._bus_id = i2c_bus
        self._addr = i2c_address
        self._external_vcc = external_vcc
        self._reset_pin = reset_pin
        self._font_path = font_path
        self._font_size = font_size
        self._font_format = font_format

    def __enter__(self) -> Self:
        self._bus = SMBus(self._bus_id)
        self._image = Image.new("1", (self._width, self._height))
        self._buffer = bytearray(((self._height // 8) * self._width) + 1)
        self._buffer[0] = 0x40  # Co=0, D/C=1 for data

        if self.can_reset():
            assert self.reset_pin is not None
            assert GPIO is not None
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.reset_pin, GPIO.OUT)
            self.reset()

        if not self._font_path:
            self._font_path = FONT_FOLDER / "DejaVuSansMono.ttf"

        match self._font_format:
            case constants.FontType.TTF | constants.FontType.OTF:
                self._font = ImageFont.truetype(self._font_path.resolve(), self._font_size)
            case constants.FontType.BITMAP:
                self._font = BitmapFont.load(str(self._font_path.resolve()))

        self.init_display()
        self.fill(constants.Colour.BLACK)
        self.show()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        try:
            if self.can_reset():
                self.reset()
            self.power_off()
        finally:
            self._bus.close()
            if self.can_reset():
                assert self.reset_pin is not None
                assert GPIO is not None
                GPIO.cleanup(self.reset_pin)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def external_vcc(self) -> bool:
        return self._external_vcc

    @property
    def reset_pin(self) -> int | None:
        return self._reset_pin

    @property
    def bus(self) -> SMBus:
        return self._bus

    @property
    def pages(self) -> int:
        return self._height // 8

    @property
    def image(self) -> Image.Image:
        return self._image

    @image.setter
    def image(self, img: Image.Image) -> None:
        self._image = img

    @property
    def page_offset(self) -> int:
        return self._page_offset

    @property
    def column_offset(self) -> int:
        return self._column_offset

    @property
    def font(self) -> ImageFont.FreeTypeFont | BitmapFont:
        return self._font

    @property
    def font_format(self) -> constants.FontType:
        return self._font_format

    @property
    def font_folder_path(self) -> pathlib.Path:
        return FONT_FOLDER

    @staticmethod
    def available_fonts() -> dict[str, pathlib.Path]:
        """Map every bundled font name to its path. Names are the allowlist for untrusted input."""
        fonts = {p.name: p for p in FONT_FOLDER.iterdir() if p.suffix.lower() in (".ttf", ".otf")}
        fonts.update({name: FONT_FOLDER / name for name in list_fonts(str(FONT_FOLDER))})
        return fonts

    @font.setter
    def font(self, font_path: pathlib.Path) -> None:
        if font_path.suffix.lower() in (".ttf", ".otf"):
            font_format = constants.FontType.TTF if font_path.suffix.lower() == ".ttf" else constants.FontType.OTF
            self._font = ImageFont.truetype(font_path.resolve(), self._font_size)
        else:
            font_format = constants.FontType.BITMAP
            self._font = BitmapFont.load(str(font_path.resolve()))

        self._font_path = font_path
        self._font_format = font_format

    @property
    def font_size(self) -> int:
        return self._font_size

    @font_size.setter
    def font_size(self, size: int) -> None:
        if self._font_format == constants.FontType.BITMAP:
            raise ValueError("Cannot set font size for bitmap fonts")
        self._font_size = size
        if self._font_path:
            self._font = ImageFont.truetype(self._font_path.resolve(), self._font_size)

    def gpio_write(self, pin: int, value: bool | Literal[0, 1]) -> None:
        if GPIO:
            GPIO.output(pin, value)
        else:
            raise RuntimeError("GPIO library not available")

    def write_command(self, command: int) -> None:
        self._bus.write_i2c_block_data(self._addr, 0x80, [command])

    def write_framebuf(self) -> None:
        """Blast out the frame buffer using I2C transactions."""
        # The first byte of self._buffer is 0x40 (data mode)
        # Send in chunks due to I2C buffer limitations (32 bytes max per transaction)
        # Skip the 0x40 prefix byte and send data with 0x40 control byte
        data = memoryview(self._buffer)[1:]  # Skip the leading 0x40
        chunk_size = 31  # Leave room for control byte
        for i in range(0, len(data), chunk_size):
            chunk = list(data[i : i + chunk_size])
            self._bus.write_i2c_block_data(self._addr, 0x40, chunk)

    def init_display(self) -> None:
        raise NotImplementedError("Subclasses must implement init_display()")

    def pixel(self, x: int, y: int, colour: constants.Colour) -> None:
        """Set a pixel at (x,y) to the given colour."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return  # Pixel out of bounds

        page = y // 8
        shift = y % 8
        index = 1 + (page * self.width) + x  # +1 for buffer control byte

        if colour == constants.Colour.WHITE:
            self._buffer[index] |= 1 << shift
        else:
            self._buffer[index] &= ~(1 << shift)

        self._image.putpixel((x, y), colour)
        self.show()

    def fill(self, colour: constants.Colour) -> None:
        """Fill the display buffer with the given colour."""
        fill_byte = 0xFF if colour == constants.Colour.WHITE else 0x00
        for i in range(1, len(self._buffer)):
            self._buffer[i] = fill_byte

        self.image.paste(colour, (0, 0, self.width, self.height))
        self.show()

    def text(self, string: str, x: int, y: int) -> None:
        """Draw text at the given (x,y) position."""
        match self._font_format:
            case constants.FontType.TTF | constants.FontType.OTF:
                draw = ImageDraw.Draw(self._image)
                draw.text((x, y), string, font=self.font, fill=constants.Colour.WHITE)  # type: ignore
            case constants.FontType.BITMAP:
                assert isinstance(self._font, BitmapFont)
                self._font.render_text(self._image, (x, y), string)

        self.show()

    def show(self) -> None:
        """Update the display."""
        self._image_to_buffer()
        # Set column address with offset
        xpos0 = 0
        xpos1 = self.width - 1
        if self.width == 64:
            # displays with width of 64 pixels are shifted by 32
            xpos0 += 32
            xpos1 += 32
        self.write_command(constants.SET_COLUMN_ADDRESS)
        self.write_command(xpos0 + self._column_offset)
        self.write_command(xpos1 + self._column_offset)
        self.write_command(constants.SET_PAGE_ADDRESS)
        self.write_command(0)
        self.write_command(self.pages - 1)
        self.write_framebuf()

    def _image_to_buffer(self) -> None:
        """Convert PIL image to buffer."""
        for page in range(self.pages):
            band = self._image.crop((0, page * 8, self.width, page * 8 + 8))
            # ROTATE_270 lands each column in one row, so mode "1" tobytes() packs
            # it straight into the page's column-major bytes.
            start = 1 + page * self.width
            self._buffer[start : start + self.width] = band.transpose(Image.Transpose.ROTATE_270).tobytes()

    def power_off(self) -> None:
        """Turn off the display."""
        self.write_command(constants.DISPLAY_OFF)

    def can_reset(self) -> bool:
        return self.reset_pin is not None and GPIO is not None

    def reset(self) -> None:
        if not self.can_reset():
            return
        assert self.reset_pin is not None
        self.gpio_write(self.reset_pin, 1)
        time.sleep(0.05)
        self.gpio_write(self.reset_pin, 0)
        time.sleep(0.05)
        self.gpio_write(self.reset_pin, 1)
        # The controller needs to settle before it will accept commands. The
        # previous 10ms pulse left the panel wedged after an unclean shutdown,
        # needing a manual reset before the service would come up.
        time.sleep(0.3)


class SSD1305_128x32(SSD1305):
    def __init__(
        self,
        width: int = 128,
        height: int = 32,
        i2c_bus: int = 1,
        i2c_address: int = constants.SSD1305_I2C_ADDRESS,
        external_vcc: bool = False,
        reset_pin: int | None = 4,
        font_path: pathlib.Path | None = None,
        font_size: int = 8,
        font_format: constants.FontType = constants.FontType.TTF,
    ) -> None:
        self._page_offset = 4
        self._column_offset = 4
        super().__init__(
            width, height, i2c_bus, i2c_address, external_vcc, reset_pin, font_path, font_size, font_format
        )

    def init_display(self) -> None:
        for cmd in (
            constants.DISPLAY_OFF,
            constants.SET_DISPLAY_CLOCK_DIV,
            0x80,
            constants.SEGMENT_REMAP | 0x01,
            constants.SET_MULTIPLEX,
            self.height - 1,
            constants.SET_DISPLAY_OFFSET,
            0x00,
            constants.MASTER_CONFIG,
            0x8E,
            constants.SET_AREA_COLOUR,
            0x05,
            constants.SET_MEMORY_MODE,
            0x00,
            constants.SET_START_LINE,
            0x2E,
            constants.COM_SCAN_DEC,
            constants.SET_COM_PIN_CFG,
            0x12,
            constants.SET_LUT,
            0x3F,
            0x3F,
            0x3F,
            constants.SET_CONTRAST,
            0xFF,
            constants.SET_PRECHARGE,
            0xD2,
            constants.SET_VCOM_LEVEL,
            0x34,
            constants.NORMAL_DISPLAY,
            constants.DISPLAY_ALL_ON_RESUME,
            constants.SET_CHARGE_PUMP,
            0x10 if self.external_vcc else 0x14,
            constants.DISPLAY_ON,
        ):
            self.write_command(cmd)


class SSD1305_128x64(SSD1305):
    def __init__(
        self,
        width: int = 128,
        height: int = 64,
        i2c_bus: int = 1,
        i2c_address: int = constants.SSD1305_I2C_ADDRESS,
        external_vcc: bool = False,
        reset_pin: int | None = None,
        font_path: pathlib.Path | None = None,
        font_size: int = 8,
        font_format: constants.FontType = constants.FontType.TTF,
    ) -> None:
        self._page_offset = 0
        self._column_offset = 4
        super().__init__(
            width, height, i2c_bus, i2c_address, external_vcc, reset_pin, font_path, font_size, font_format
        )

    def init_display(self) -> None:
        raise NotImplementedError("SSD1305_128x64 init sequence is not defined yet")


if __name__ == "__main__":
    from time import sleep

    with SSD1305_128x32(
        font_path=pathlib.Path("adafruit_ssd1305/fonts/small_6x8"), font_format=constants.FontType.BITMAP
    ) as display:
        for i in range(10):
            display.fill(constants.Colour.WHITE)
            sleep(0.5)
            display.fill(constants.Colour.BLACK)
            sleep(0.5)

        display.text("Hello, World!", 0, 0)
        display.text("SSD1305 Test", 0, 8)
        display.text("Displaying text", 0, 16)
        sleep(5)
        print(display.font_folder_path)
