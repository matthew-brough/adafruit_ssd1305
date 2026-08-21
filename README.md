# SSD1305 OLED Display Driver

A CPython driver for the SSD1305 monochrome OLED display, designed for Raspberry Pi and other Linux-based systems.

> **Note:** This is not an official Adafruit library. It is an independent implementation for the SSD1305 display controller.

## Features

- I2C communication via `smbus3`
- Support for 128x32 and 128x64 display configurations
- TrueType (TTF) and OpenType (OTF) font rendering via Pillow
- Bitmap font support for pixel-perfect text
- Optional GPIO reset pin support for Raspberry Pi
- Context manager support for clean resource handling

## Installation

Not published to PyPI — install from the repository:

```bash
pip install git+https://github.com/matthew-brough/adafruit_ssd1305.git
```

### With GPIO Support (Raspberry Pi)

```bash
pip install 'adafruit_ssd1305[gpio] @ git+https://github.com/matthew-brough/adafruit_ssd1305.git'
```

## Requirements

- Python 3.10+
- Pillow
- smbus3
- RPi.GPIO (optional, for reset pin support on Raspberry Pi)

## Usage

### Basic Example

```python
from adafruit_ssd1305 import SSD1305_128x32, constants

with SSD1305_128x32() as display:
    display.text("Hello, World!", 0, 0)
    display.text("Line 2", 0, 8)
```

### Using Custom Fonts

```python
import pathlib
from adafruit_ssd1305 import SSD1305_128x32, constants

# TrueType font
with SSD1305_128x32(
    font_path=pathlib.Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    font_size=10
) as display:
    display.text("Custom Font!", 0, 0)
```

### Using Bitmap Fonts

```python
import pathlib
from adafruit_ssd1305 import SSD1305_128x32, constants

with SSD1305_128x32(
    font_path=pathlib.Path("path/to/bitmap_font"),
    font_format=constants.FontType.BITMAP
) as display:
    display.text("Pixel Perfect!", 0, 0)
```

### Accessing Included Fonts

```python
from adafruit_ssd1305 import SSD1305_128x32, constants

with SSD1305_128x32() as display:
    fonts_dir = display.font_folder_path
    print(f"Included fonts: {list(fonts_dir.iterdir())}")
```

### Drawing Pixels

```python
from adafruit_ssd1305 import SSD1305_128x32, constants

with SSD1305_128x32() as display:
    display.pixel(10, 10, constants.Colour.WHITE)
    display.fill(constants.Colour.BLACK)
```

## Display Classes

| Class | Resolution | Default Column Offset | Default Page Offset |
|-------|------------|----------------------|---------------------|
| `SSD1305_128x32` | 128x32 | 4 | 4 |
| `SSD1305_128x64` | 128x64 | 4 | 0 |

## Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `width` | int | varies | Display width in pixels |
| `height` | int | varies | Display height in pixels |
| `i2c_bus` | int | 1 | I2C bus number |
| `i2c_address` | int | 0x3C | I2C device address |
| `external_vcc` | bool | False | External VCC power supply |
| `reset_pin` | int \| None | None/4 | GPIO pin for reset (BCM numbering) |
| `font_path` | Path \| None | None | Path to font file or directory |
| `font_size` | int | 8 | Font size (TTF/OTF only) |
| `font_format` | FontType | TTF | Font format (TTF, OTF, or BITMAP) |

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE.md](LICENSE.md) file for details.
