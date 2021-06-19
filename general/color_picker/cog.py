import colorsys
import io
import re

from PIL import ImageColor, Image
from discord import Embed, Colour, File
from discord.ext import commands
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.translations import t
from ...contributor import Contributor

t = t.color_picker


class ColorPickerCog(Cog, name="Color Picker"):
    CONTRIBUTORS = [Contributor.Tert0]

    RE_HEX = re.compile(r"^#([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$")
    RE_RGB = re.compile(r"^rgb\(([0-9]{1,3})\, ?([0-9]{1,3})\, ?([0-9]{1,3})\)$")
    RE_HSV = re.compile(r"^hsv\(([0-9]{1,3})\, ?([0-9]{1,3})\, ?([0-9]{1,3})\)$")
    RE_HSL = re.compile(r"^hsl\(([0-9]{1,3})\, ?([0-9]{1,3})\, ?([0-9]{1,3})\)$")

    @commands.command(name="color_picker", aliases=["cp", "color"])
    async def color_picker(self, ctx: Context, *, color: str):
        if color_re := self.RE_HEX.match(color):
            color_hex = color_re.group(1)
            rgb: tuple[int] = ImageColor.getcolor(color, "RGB")
            hsv: tuple[int] = ImageColor.getcolor(color, "HSV")
            hsl = tuple(map(int, colorsys.rgb_to_hls(*rgb)))  # skipcq: PYL-E1120
        elif color_re := self.RE_RGB.match(color):
            rgb = (int(color_re.group(1)), int(color_re.group(2)), int(color_re.group(3)))
            color_hex = "%02x%02x%02x" % rgb
            hsv: tuple[int] = ImageColor.getcolor(f"#{color_hex}", "HSV")
            hsl = tuple(map(int, colorsys.rgb_to_hls(*rgb)))  # skipcq: PYL-E1120
        elif color_re := self.RE_HSV.match(color):
            hsv: tuple[int] = (int(color_re.group(1)), int(color_re.group(2)), int(color_re.group(3)))
            rgb = tuple(map(int, colorsys.hsv_to_rgb(*hsv)))  # skipcq: PYL-E1120
            color_hex = "%02x%02x%02x" % rgb
            hsl = tuple(map(int, colorsys.rgb_to_hls(*rgb)))  # skipcq: PYL-E1120
        elif color_re := self.RE_HSL.match(color):
            hsl: tuple[int] = (int(color_re.group(1)), int(color_re.group(2)), int(color_re.group(3)))
            rgb = tuple(map(int, colorsys.hls_to_rgb(*hsl)))  # skipcq: PYL-E1120
            hsv = tuple(map(int, colorsys.rgb_to_hsv(*rgb)))  # skipcq: PYL-E1120
            color_hex = "%02x%02x%02x" % rgb
        else:
            embed: Embed = Embed(title=t.error_parse_color_title(color), description=t.error_parse_color_example)
            await reply(ctx, embed=embed)
            return
        img: Image = Image.new("RGB", (100, 100), rgb)
        with io.BytesIO() as image_binary:
            img.save(image_binary, "PNG")
            image_binary.seek(0)
            embed: Embed = Embed(title="Color Picker", color=Colour(int(color_hex, 16)))
            embed.add_field(name="HEX", value=f"#{color_hex}")
            embed.add_field(name="RGB", value=f"rgb{rgb}")
            embed.add_field(name="HSV", value=f"hsv{hsv}")
            embed.add_field(name="HSL", value=f"hsl{hsl}")
            embed.set_image(url="attachment://color.png")
            await reply(ctx, embed=embed, file=File(fp=image_binary, filename="color.png"))
