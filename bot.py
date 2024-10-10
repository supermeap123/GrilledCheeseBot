import discord
from discord.ext import commands
from config import DISCORD_TOKEN, logger
from database import init_database
from cogs.grilled_cheese_cog import GrilledCheeseCog


intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True  # Required to read message content

bot = commands.Bot(command_prefix='g!', intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    init_database()
    await bot.add_cog(GrilledCheeseCog(bot))


if __name__ == '__main__':
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"Failed to start the bot: {e}")
