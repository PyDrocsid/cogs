import colorsys
import re
from typing import Any

from discord import Colour, Embed
from discord.ext import commands
from discord.ext.commands import CommandError, Context

from PyDrocsid.cog import Cog
from PyDrocsid.command import docs, reply
from PyDrocsid.translations import t

from ...contributor import Contributor


t = t.color_picker


def _convert_to_floats(given: list[tuple[int, ...]]) -> tuple[float, ...]:
    """3 tuples (number from user, max-value)"""
    out: list[float] = []

    for arg in given:
        if int(arg[0]) < 0:
            out.append(0.0)
        elif int(arg[0]) > arg[1]:
            out.append(1.0)
        else:
            out.append(float(int(arg[0]) / arg[1]))

    return out[0], out[1], out[2]


def _to_rgb(colors: tuple[Any, Any, Any]) -> tuple[int, ...]:
    out: list[int] = []

    for color in colors:
        if int(color) < 0:
            out.append(0)
        if int(color) > 255:
            out.append(255)
        else:
            out.append(int(color))

    return out[0], out[1], out[2]


def _hex_to_color(hex_color: str) -> tuple[int, ...]:
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # noqa: E203


class ColorPickerCog(Cog, name="Color Picker"):
    CONTRIBUTORS = [Contributor.Tert0, Contributor.NekoFanatic]

    RE_HEX = re.compile(r"^#?([a-fA-F0-9]{6}|[a-fA-F0-9]{3})$")
    RE_RGB = re.compile(r"^rgb\(([0-9]{1,3}), *([0-9]{1,3}), *([0-9]{1,3})\)$")
    RE_HSV = re.compile(r"^hsv\(([0-9]{1,3}), *([0-9]{1,3}), *([0-9]{1,3})\)$")
    RE_HLS = re.compile(r"^hls\(([0-9]{1,3}), *([0-9]{1,3}), *([0-9]{1,3})\)$")

    @commands.command(name="color_picker", aliases=["cp", "color"])
    @docs(t.commands.color_picker)
    async def color_picker(self, ctx: Context, *, color: str):

        if color_re := self.RE_HEX.match(color):
            rgb = _hex_to_color(color_re.group(1))

        elif color_re := self.RE_RGB.match(color):
            rgb = _to_rgb((color_re.group(1), color_re.group(2), color_re.group(3)))

        elif color_re := self.RE_HLS.match(color):
            values = _convert_to_floats([(color_re.group(1), 359), (color_re.group(2), 100), (color_re.group(3), 100)])
            rgb = colorsys.hls_to_rgb(values[0], values[1], values[2])
            rgb = tuple(int(color * 255) for color in rgb)

        elif color_re := self.RE_HSV.match(color):
            values = _convert_to_floats([(color_re.group(1), 359), (color_re.group(2), 100), (color_re.group(3), 100)])
            rgb = colorsys.hsv_to_rgb(values[0], values[1], values[2])
            rgb = tuple(int(color * 255) for color in rgb)

        else:
            raise CommandError(t.error_parse_color_example(color))

        color_hex = f"{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
        hsv = colorsys.rgb_to_hsv(*rgb)
        h, s, v = hsv
        hsv = (int(h * 360), int(s * 100), int(v))

        hls = colorsys.rgb_to_hls(*rgb)
        h, l, s = hls
        hls = (int(h * 360), int(s * 100), int(v))

        embed: Embed = Embed(title="Color Picker", color=Colour(int(color_hex, 16)))
        embed.set_image(url=f"https://singlecolorimage.com/get/{color_hex}/300x50")
        embed.add_field(name="HEX", value=f"`#{color_hex}`")
        embed.add_field(name="RGB", value=f"`rgb{rgb}`")
        embed.add_field(name="HSV", value=f"`hsv{hsv}`")
        embed.add_field(name="HLS", value=f"`hsl{hls}`")

        await reply(ctx, embed=embed)
