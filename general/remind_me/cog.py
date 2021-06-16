from discord import Message, Member, PartialEmoji, Forbidden

from PyDrocsid.cog import Cog
from PyDrocsid.emojis import name_to_emoji
from ...contributor import Contributor

EMOJIS = {
    name_to_emoji["star"],
    name_to_emoji["mailbox"],
    name_to_emoji["e_mail"],
    name_to_emoji["envelope"],
    name_to_emoji["incoming_envelope"],
    name_to_emoji["envelope_with_arrow"],
    name_to_emoji["floppy_disk"],
}


class RemindMeCog(Cog, name="RemindMe"):
    CONTRIBUTORS = [Contributor.Tristan]

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        if str(emoji) not in EMOJIS or member.bot or message.guild is None:
            return

        if message.attachments:
            try:
                await member.send("\n".join(attachment.url for attachment in message.attachments))
                await message.remove_reaction(emoji, member)
            except Forbidden:
                await message.remove_reaction(emoji, member)
                return

        embed = message.embeds[0] if message.embeds else None

        if message.content or embed:
            try:
                await member.send(message.content, embed=embed)
                await message.remove_reaction(emoji, member)
            except Forbidden:
                await message.remove_reaction(emoji, member)
