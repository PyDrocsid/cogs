import colorsys
import io
import re
from typing import Any

from discord import Embed, Colour, File
from discord.ext import commands
from discord.ext.commands import Context, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply
from PyDrocsid.translations import t
from ...contributor import Contributor

t = t.color_picker


class ColorPickerCog(Cog, name="Color Picker"):
    CONTRIBUTORS = [Contributor.Tert0]

    RE_HEX = re.compile(r"^#?([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$")
    RE_RGB = re.compile(r"^rgb\(([0-9]{1,3}), *([0-9]{1,3}), *([0-9]{1,3})\)$")
    RE_HSV = re.compile(r"^hsv\(([0-9]{1,3}), *([0-9]{1,3}), *([0-9]{1,3})\)$")
    RE_HSL = re.compile(r"^hsl\(([0-9]{1,3}), *([0-9]{1,3}), *([0-9]{1,3})\)$")

    @commands.command(name="color_picker", aliases=["cp", "color"])
    async def color_picker(self, ctx: Context, *, color: str):
        def _to_int(colors: tuple[Any, Any, Any]) -> tuple[int, ...]:
            return tuple(map(int, colors))

        color_hex: str
        rgb: tuple[int, ...]
        hsv: tuple[int, ...]
        hsl: tuple[int, ...]

        def _hex_to_color(hex_color: str) -> tuple[int, ...]:
            return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # noqa: E203

        if color_re := self.RE_HEX.match(color):
            color_hex = color_re.group(1)
            rgb = _hex_to_color(color_hex)
            hsv = _to_int(colorsys.rgb_to_hsv(*rgb))
            hsl = _to_int(colorsys.rgb_to_hls(*rgb))
        elif color_re := self.RE_RGB.match(color):
            rgb = _to_int((color_re.group(1), color_re.group(2), color_re.group(3)))
            color_hex = "{0:02x}{1:02x}{2:02x}".format(*rgb)
            hsv = _to_int(colorsys.rgb_to_hsv(*rgb))
            hsl = _to_int(colorsys.rgb_to_hls(*rgb))
        elif color_re := self.RE_HSV.match(color):
            hsv = _to_int((color_re.group(1), color_re.group(2), color_re.group(3)))
            rgb = _to_int(colorsys.hsv_to_rgb(*hsv))
            color_hex = "{0:02x}{1:02x}{2:02x}".format(*rgb)
            hsl = _to_int(colorsys.rgb_to_hls(*rgb))
        elif color_re := self.RE_HSL.match(color):
            hsl = _to_int((color_re.group(1), color_re.group(2), color_re.group(3)))
            rgb = _to_int(colorsys.hls_to_rgb(*hsl))
            hsv = _to_int(colorsys.rgb_to_hsv(*rgb))
            color_hex = "{0:02x}{1:02x}{2:02x}".format(*rgb)
        else:
            raise CommandError(t.error_parse_color_example(color))

        embed: Embed = Embed(title="Color Picker", color=Colour(int(color_hex, 16)))
        embed.set_image(url=f"https://singlecolorimage.com/get/{color_hex}/300x50")
        embed.add_field(name="HEX", value=f"`#{color_hex}`")
        embed.add_field(name="RGB", value=f"`rgb{rgb}`")
        embed.add_field(name="HSV", value=f"`hsv{hsv}`")
        embed.add_field(name="HSL", value=f"`hsl{hsl}`")
        await reply(ctx, embed=embed)
