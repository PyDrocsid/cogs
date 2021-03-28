# -*- coding: utf-8 -*-

"""
The MIT License (MIT)
Copyright (c) 2017 Rapptz
AutoModPermission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
---

This whole cog is basically copied from:
https://github.com/Rapptz/RoboDanny/
"""

import io
import os
import re
import zlib
from typing import Iterable, Optional, Callable

import aiohttp
import discord
from discord import Embed
from discord.ext import commands
from discord.ext.commands import Context

from PyDrocsid.cog import Cog
from PyDrocsid.environment import CACHE_TTL
from PyDrocsid.logger import get_logger
from PyDrocsid.permission import BasePermission
from PyDrocsid.redis import redis
from PyDrocsid.translations import t
from PyDrocsid.util import reply
from .colors import Colors
from ...contributor import Contributor

tg = t.g
t = t.discordpy_documentation

logger = get_logger(__name__)


def finder(text: str, collection: Iterable, *, key: Optional[Callable[..., str]] = None):
    suggestions = []
    regex = re.compile(".*?".join(map(re.escape, text.replace(" ", ""))), flags=re.IGNORECASE)
    for item in collection:
        to_search = key(item) if key else item
        if r := regex.search(to_search):
            suggestions.append((len(r.group()), r.start(), item))

    return [z for *_, z in sorted(suggestions, key=lambda tup: (tup[0], tup[1], key(tup[2])) if key else tup)]


class SphinxObjectFileReader:
    # Inspired by Sphinx's InventoryFileReader
    BUFSIZE = 16 * 1024

    def __init__(self, buffer: bytes):
        self.stream = io.BytesIO(buffer)

    def readline(self):
        return self.stream.readline().decode()

    def skipline(self):
        self.stream.readline()

    def read_compressed_chunks(self):
        decompressor = zlib.decompressobj()
        while True:
            chunk = self.stream.read(self.BUFSIZE)
            if len(chunk) == 0:
                break
            yield decompressor.decompress(chunk)
        yield decompressor.flush()

    def read_compressed_lines(self):
        buf = b""
        for chunk in self.read_compressed_chunks():
            buf += chunk
            while True:
                pos = buf.find(b"\n")
                if pos == -1:
                    break
                yield buf[:pos].decode()
                pos += 1
                buf = buf[pos:]


def parse_object_inv(stream: SphinxObjectFileReader, url: str):
    # key: URL
    # n.b.: key doesn't have `discord` or `discord.ext.commands` namespaces
    result = {}

    # first line is version info
    inv_version = stream.readline().rstrip()

    if inv_version != "# Sphinx inventory version 2":
        raise RuntimeError("Invalid objects.inv file version.")

    # next line is "# Project: <name>"
    # then after that is "# Version: <version>"
    projname = stream.readline().rstrip()[11:]
    stream.readline()

    # next line says if it's a zlib header
    line = stream.readline()
    if "zlib" not in line:
        raise RuntimeError("Invalid objects.inv file, not z-lib compatible.")

    # This code mostly comes from the Sphinx repository.
    entry_regex = re.compile(r"(?x)(.+?)\s+(\S*:\S*)\s+(-?\d+)\s+(\S+)\s+(.*)")
    for line in stream.read_compressed_lines():
        match = entry_regex.match(line.rstrip())
        if not match:
            continue

        name, directive, _, location, dispname = match.groups()
        domain, _, subdirective = directive.partition(":")
        if directive == "py:module" and name in result:
            # From the Sphinx Repository:
            # due to a bug in 1.1 and below,
            # two inventory entries are created
            # for Python modules, and the first
            # one is correct
            continue

        # Most documentation pages have a label
        if directive == "std:doc":
            subdirective = "label"

        if location.endswith("$"):
            location = location[:-1] + name

        key = name if dispname == "-" else dispname
        prefix = f"{subdirective}:" if domain == "std" else ""

        if projname == "discord.py":
            key = key.replace("discord.ext.commands.", "").replace("discord.", "")

        result[f"{prefix}{key}"] = os.path.join(url, location)

    return result


async def build_rtfm_lookup_table(key: str, page: str) -> dict[str, str]:
    async with aiohttp.ClientSession() as session:
        resp = await session.get(page + "/objects.inv")
        if resp.status != 200:
            logger.warning(f"Documentation for {key} ({page}) could not be loaded ({resp.status})")
            return {}

        stream = SphinxObjectFileReader(await resp.read())
        return parse_object_inv(stream, page)


async def get_lookup_table(ctx: Context, name: str, url: str) -> dict[str, str]:
    if table := await redis.hgetall(key := f"pydoc:name={name}"):
        return table

    await ctx.trigger_typing()
    logger.debug(f"loading documentation for {name} ({url})")
    table = await build_rtfm_lookup_table(name, url)
    if table:
        logger.debug(f"documentation for {name} ({url}) has been loaded")

    await redis.hmset_dict(key, table)
    await redis.expire(key, CACHE_TTL)
    return table


async def do_rtfm(ctx: Context, key: str, obj: Optional[str]):
    page_types = {"discord.py": "https://discordpy.readthedocs.io/en/latest", "python": "https://docs.python.org/3"}

    if obj is None:
        embed = Embed(
            title=t.documentation(key.capitalize()),
            description=page_types[key],
            colour=Colors.DiscordPy,
        )
        return await reply(ctx, embed=embed)

    obj = re.sub(r"^(?:discord\.(?:ext\.)?)?(?:commands\.)?(.+)", r"\1", obj)

    if key.startswith("discord.py"):
        # point the abc.Messageable types properly:
        q = obj.lower()
        for name in dir(discord.abc.Messageable):
            if name[0] == "_":
                continue
            if q == name:
                obj = f"abc.Messageable.{name}"
                break

    table = await get_lookup_table(ctx, key, page_types[key])

    matches = finder(obj, table.items(), key=lambda x: x[0])[:10]

    if not matches:
        embed = Embed(
            title=t.documentation(key.capitalize()),
            description=t.no_results,
            colour=Colors.error,
        )
        return await reply(ctx, embed=embed)

    e = discord.Embed(colour=Colors.DiscordPy, title=t.documentation(key.capitalize()))
    e.description = "\n".join(f"[`{key}`]({url})" for key, url in matches)
    e.set_footer(text=tg.requested_by(ctx.author, ctx.author.id), icon_url=ctx.author.avatar_url)
    await reply(ctx, embed=e)


class DiscordpyDocumentationCog(Cog, name="Discordpy Documentation"):
    """
    Cog to have fancy discordpy doc embeds

    thanks danny :)
    """

    CONTRIBUTORS = [Contributor.pohlium, Contributor.Defelo, Contributor.wolflu]
    PERMISSIONS = BasePermission

    @commands.command(aliases=["dpy"])
    async def dpy_docs(self, ctx: Context, *, obj: str = None):
        """
        search the official discord.py documentation
        """

        await do_rtfm(ctx, "discord.py", obj)

    @commands.command(aliases=["py"])
    async def py_docs(self, ctx: Context, *, obj: str = None):
        """
        search the official python documentation
        """

        await do_rtfm(ctx, "python", obj)
