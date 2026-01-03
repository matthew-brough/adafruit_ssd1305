"""
Bitmap Font module for Pillow

Usage:
    from converted.bitmap_font import BitmapFont
    
    # Load a font
    font = BitmapFont.load('converted/sinclair_8x8')
    
    # Create an image and render text
    from PIL import Image
    img = Image.new('1', (128, 64), 0)
    font.render_text(img, (0, 0), "Hello World!")
    
    # Or use with ImageDraw (limited compatibility)
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    # Note: For full compatibility, use font.render_text() directly
"""

import os
import json
from PIL import Image


class BitmapFont:
    """A bitmap font class for use with Pillow."""
    
    def __init__(self, sprite: Image.Image, metrics: dict):
        self.sprite = sprite
        self.metrics = metrics
        self.width = metrics['width']
        self.height = metrics['height']
        self.chars = metrics['chars']
    
    @classmethod
    def load(cls, font_dir: str) -> 'BitmapFont':
        """Load a converted bitmap font from a directory."""
        sprite_path = os.path.join(font_dir, 'sprite.png')
        metrics_path = os.path.join(font_dir, 'metrics.json')
        
        sprite = Image.open(sprite_path).convert('1')
        
        with open(metrics_path, 'r', encoding='utf-8') as f:
            metrics = json.load(f)
        
        return cls(sprite, metrics)
    
    def get_char_image(self, char: str) -> Image.Image | None:
        """Get the image for a single character."""
        if char not in self.chars:
            return None
        
        info = self.chars[char]
        x, y = info['x'], info['y']
        w, h = info['width'], info['height']
        
        return self.sprite.crop((x, y, x + w, y + h))
    
    def getbbox(self, text: str) -> tuple[int, int, int, int]:
        """Get the bounding box for rendered text."""
        text_width = sum(
            self.chars.get(c, {}).get('width', self.width)
            for c in text
        )
        return (0, 0, text_width, self.height)
    
    def getmask(self, text: str) -> Image.Image:
        """Get a mask image for the text."""
        bbox = self.getbbox(text)
        mask = Image.new('1', (bbox[2], bbox[3]), 0)
        
        x = 0
        for char in text:
            char_img = self.get_char_image(char)
            if char_img:
                mask.paste(char_img, (x, 0))
                x += self.chars[char]['width']
            else:
                x += self.width
        
        return mask
    
    def render_text(self, image: Image.Image, position: tuple[int, int], 
                    text: str, fill: int = 1) -> None:
        """
        Render text onto an image.
        
        Args:
            image: PIL Image to draw on
            position: (x, y) position for text
            text: Text to render
            fill: Pixel value (1 for white on mode '1' images)
        """
        x, y = position
        text = text.upper()
        for char in text:
            char_img = self.get_char_image(char)
            if char_img:
                if image.mode == '1':
                    if fill:
                        image.paste(char_img, (x, y))
                    else:
                        from PIL import ImageOps
                        inverted = ImageOps.invert(char_img.convert('L')).convert('1')
                        image.paste(inverted, (x, y))
                else:
                    image.paste(char_img, (x, y))
                x += self.chars[char]['width']
            else:
                x += self.width
    
    def text_size(self, text: str) -> tuple[int, int]:
        """Get the size of rendered text."""
        bbox = self.getbbox(text)
        return (bbox[2], bbox[3])


def list_fonts(converted_dir: str) -> list[str]:
    """List all available converted fonts."""
    fonts = []
    for item in os.listdir(converted_dir):
        font_path = os.path.join(converted_dir, item)
        if os.path.isdir(font_path):
            metrics_path = os.path.join(font_path, 'metrics.json')
            if os.path.exists(metrics_path):
                fonts.append(item)
    return sorted(fonts)
