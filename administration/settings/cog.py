import string

from discord import Embed
from discord.ext import commands
from discord.ext.commands import guild_only, Context, CommandError

from PyDrocsid.cog import Cog
from PyDrocsid.command import reply, docs
from PyDrocsid.prefix import set_prefix, GlobalPrefix
from PyDrocsid.translations import t
from .colors import Colors
from .permissions import SettingsPermission
from ...contributor import Contributor
from ...pubsub import send_to_changelog

tg = t.g
t = t.settings


class SettingsCog(Cog, name="Settings"):
    CONTRIBUTORS = [Contributor.Defelo]

    @commands.command(aliases=["prefix"])
    @SettingsPermission.change_prefix.check
    @guild_only()
    @docs(t.commands.local_prefix)
    async def local_prefix(self, ctx: Context, *, new_prefix: str):
        if not 0 < len(new_prefix) <= 16:
            raise CommandError(t.invalid_prefix_length)

        valid_chars = set(string.ascii_letters + string.digits + string.punctuation) - {"`"}
        if any(c not in valid_chars for c in new_prefix):
            raise CommandError(t.prefix_invalid_chars)

        await set_prefix(ctx.guild, new_prefix)
        embed = Embed(title=t.prefix, description=t.local_prefix_updated, colour=Colors.prefix)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_local_prefix_updated(new_prefix))

    @commands.command()
    @SettingsPermission.change_prefix.check
    @guild_only()
    @docs(t.commands.global_prefix)
    async def global_prefix(self, ctx: Context, *, new_prefix: str):
        if not 0 < len(new_prefix) <= 16:
            raise CommandError(t.invalid_prefix_length)

        valid_chars = set(string.ascii_letters + string.digits)
        if any(c not in valid_chars for c in new_prefix):
            raise CommandError(t.prefix_invalid_chars)

        for cmd in self.bot.commands:
            if new_prefix.lower() in [cmd.name.lower(), *map(str.lower, cmd.aliases)]:
                raise CommandError(t.global_prefix_not_available)

        other_guild_id = await GlobalPrefix.get_guild(new_prefix)
        if other_guild_id and other_guild_id != ctx.guild.id:
            raise CommandError(t.global_prefix_not_available)

        await GlobalPrefix.set_prefix(ctx.guild.id, new_prefix)
        embed = Embed(title=t.prefix, description=t.global_prefix_updated, colour=Colors.prefix)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_global_prefix_updated(new_prefix))

    @commands.command()
    @SettingsPermission.change_prefix.check
    @guild_only()
    @docs(t.commands.remove_global_prefix)
    async def remove_global_prefix(self, ctx: Context):
        if not await GlobalPrefix.get_prefix(ctx.guild.id):
            raise CommandError(t.no_global_prefix)

        await GlobalPrefix.clear_prefix(ctx.guild.id)
        embed = Embed(title=t.prefix, description=t.global_prefix_removed, colour=Colors.prefix)
        await reply(ctx, embed=embed)
        await send_to_changelog(ctx.guild, t.log_global_prefix_removed)
