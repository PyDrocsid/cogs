from discord import Message, Member, PartialEmoji

from PyDrocsid.cog import Cog
from PyDrocsid.emojis import name_to_emoji
from PyDrocsid.translations import t

tg = t.g
t = t.remindme

+EMOJI = {
+    name_to_emoji["star"],
+    name_to_emoji["mailbox"],
+    name_to_emoji["e_mail"],
+    name_to_emoji["envelope"],
+    name_to_emoji["incoming_envelope"],
+    name_to_emoji["envelope_with_arrow"],
+    name_to_emoji["floppy_disk"],
+}


class RemindMeCog(Cog, name="RemindMe"):
    CONTRIBUTORS = []

    async def on_raw_reaction_add(self, message: Message, emoji: PartialEmoji, member: Member):
        if str(emoji) not in EMOJI or member.bot or message.guild is None:
            return

        await member.send(message.content, embed=message.embeds[0] if message.embeds else None)
