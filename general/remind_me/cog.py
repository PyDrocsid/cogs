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
    """Add a "Remind Me"-functionality by sending the user a message they reacted on."""

    CONTRIBUTORS = [Contributor.Tristan]

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        """
        Check, if the reaction is in a list of set emojis. If so, the message is sent as a direct message to the user.
        Remove the user reaction, if the user does not accept direct messages.
        Send an alert in case of missing permissions.
        """
        if str(emoji) not in EMOJIS or member.bot or message.guild is None:
            return

        if message.attachments:
            try:
                message_to_user = await member.send("\n".join(attachment.url for attachment in message.attachments))
                message_to_user.add_reaction(name_to_emoji["wastebasket"])
            except Forbidden:
                try:
                    await message.remove_reaction(emoji, member)
                    return
                except Forbidden:
                    await send_alert(message.guild, t.cannot_send(message.jump_url))
                    return

        embed = message.embeds[0] if message.embeds else None

        if message.content or embed:
            try:
                message_to_user = await member.send(message.content, embed=embed)
                message_to_user.add_reaction(name_to_emoji["wastebasket"])
            except Forbidden:
                try:
                    await message.remove_reaction(emoji, member)
                except Forbidden:
                    await send_alert(message.guild, t.cannot_send(message.jump_url))

        if await check_wastebasket(message_to_user, member, emoji, t.created_by):
            await message.delete()
            raise StopEventHandling
