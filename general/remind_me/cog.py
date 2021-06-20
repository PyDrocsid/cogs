from discord import Message, Member, PartialEmoji, Forbidden

from PyDrocsid.cog import Cog
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.events import StopEventHandling
from PyDrocsid.translations import t
from PyDrocsid.util import check_wastebasket
from ...contributor import Contributor
from ...pubsub import send_alert

tg = t.g
t = t.remind_me

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
    """
    Adds a "Remind Me"-functionality by sending the user a message they reacted on.
    """

    CONTRIBUTORS = [Contributor.Tristan]

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        """
        Checks, if the reaction is in a list of set emojis. If so, the message is sent via private message.
        Removes the user reaction, if the user does not accept private messages.
        Sends an alert in case of missing permissions.
        """

        if message.guild is None and str(emoji) == name_to_emoji["wastebasket"] and message.author == self.bot.user:
            await message.delete()
            raise StopEventHandling

        if str(emoji) not in EMOJIS or member.bot or message.guild is None:
            return

        embed = message.embeds[0] if message.embeds else None

        if message.content or embed:
            try:
                message_to_user = await member.send(message.content, embed=embed)
                await message_to_user.add_reaction(name_to_emoji["wastebasket"])
            except Forbidden:
                try:
                    await message.remove_reaction(emoji, member)
                except Forbidden:
                    await send_alert(message.guild, t.cannot_send(message.jump_url))
