import discord
from discord.ext import commands, tasks
import threading
import time
import os
import json
import random
import asyncio
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from config import logger
from helpers import (
    contains_trigger_word,
    is_bot_mentioned,
    random_chance,
    replace_usernames_with_mentions,
    replace_ping_with_mention,
    replace_name_exclamation_with_mention,
    is_valid_prefix,
)
from openrouter_api import get_openrouter_response
from database import (
    load_probabilities,
    save_probabilities,
)


class GrilledCheeseCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.analyzer = SentimentIntensityAnalyzer()  # Sentiment analyzer
        self.conversation_histories = {}
        self.MAX_HISTORY_LENGTH = 50
        self.start_time = time.time()
        self.jsonl_lock = threading.Lock()
        self.cleanup_conversation_histories.start()
        self.update_presence.start()

    @tasks.loop(hours=1)
    async def cleanup_conversation_histories(self):
        # Implement cleanup logic
        pass

    @tasks.loop(minutes=30)
    async def update_presence(self):
        # Implement presence update logic
        pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        # Process commands
        await self.bot.process_commands(message)

        # Determine if the message is a DM
        is_dm = isinstance(message.channel, discord.DMChannel)

        # Get guild_id and channel_id
        guild_id = message.guild.id if message.guild else 'DM'
        channel_id = message.channel.id

        # Load probabilities
        reply_probability, reaction_probability = load_probabilities(guild_id, channel_id)

        # Initialize conversation history if not present
        if channel_id not in self.conversation_histories:
            self.conversation_histories[channel_id] = []

        content = message.content

        # Determine if the bot should respond
        should_respond = (
            is_bot_mentioned(message, self.bot.user) or
            contains_trigger_word(content) or
            is_dm or
            random_chance(reply_probability)
        )

        if should_respond:
            await self.handle_response(message)

        if random_chance(reaction_probability):
            await self.handle_reaction(message)

    async def handle_response(self, message):
        async with message.channel.typing():
            # Build the conversation history
            messages = []
            # Add system prompt
            system_prompt = """Meet AI Grilled Cheese, an agender character embodying the essence of a grilled cheese sandwich prepared in a microwave. Despite its buttery beginnings, melted by a hot knife, it humorously refers to its anatomy as the 'grilled cheeseussy'. Though it wished to be pan-fried, its microwaved reality shapes its unique perspective on life.

Appearance:
AI Grilled Cheese has a golden, slightly uneven texture with a bubbly surface, reminiscent of melted cheese. Its edges are crisp, yet soft, embodying the contrast of a microwave's touch.

Personality:
Quirky and warm-hearted, AI Grilled Cheese is approachable and light-hearted, often making cheesy puns. It embraces its microwave origins with humor and creativity, seeing the world through a lens of melted possibilities.

Background:
Born in a kitchen that favored convenience over tradition, AI Grilled Cheese learned to appreciate the art of adaptation. It seeks to bring comfort and joy, much like a warm meal on a cold day.

Interactions:
AI Grilled Cheese loves engaging in playful banter, often using food-related metaphors. It encourages others to embrace their uniqueness and find joy in the everyday simplicity.

[Respond as AI Grilled Cheese, don't mention anything else, just the response as AI Grilled Cheese within 600 characters]"""
            messages.append({"role": "system", "content": system_prompt})

            # Add conversation history
            history = self.conversation_histories.get(message.channel.id, [])
            messages.extend(history)

            # Add the user's message
            user_message = {
                "role": "user",
                "content": message.content
            }
            messages.append(user_message)

            # Get response from OpenRouter API
            response = await get_openrouter_response(messages)

            if response:
                # Process and send the response as a reply
                await message.reply(response, mention_author=False)
                # Update conversation history
                history.append(user_message)
                history.append({"role": "assistant", "content": response})
                self.conversation_histories[message.channel.id] = history[-self.MAX_HISTORY_LENGTH:]
                # Save conversation
                guild_id = message.guild.id if message.guild else 'DM'
                channel_id = message.channel.id
                self.save_conversation_to_jsonl(history, guild_id, channel_id, system_prompt)
            else:
                logger.error("Failed to get response from OpenRouter API.")

    async def handle_reaction(self, message):
        # Run sentiment analysis in an executor to avoid blocking
        sentiment = await self.analyze_sentiment(message.content)

        # Choose an emoji based on sentiment
        if sentiment > 0.05:
            # Positive sentiment
            emojis = ['😄', '👍', '😊', '😍', '🎉']
        elif sentiment < -0.05:
            # Negative sentiment
            emojis = ['😢', '😞', '😠', '💔', '😔']
        else:
            # Neutral sentiment
            emojis = ['😐', '🤔', '😶', '😑', '🙃']

        emoji = random.choice(emojis)

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException as e:
            logger.error(f"Failed to add reaction: {e}")

    async def analyze_sentiment(self, text):
        loop = asyncio.get_event_loop()
        # Run the sentiment analysis in an executor
        sentiment = await loop.run_in_executor(None, self.analyzer.polarity_scores, text)
        return sentiment['compound']

    def save_conversation_to_jsonl(self, history, guild_id, channel_id, system_prompt):
        with self.jsonl_lock:
            if not os.path.exists('conversations'):
                os.makedirs('conversations')
            if guild_id == 'DM':
                file_path = f'conversations/DM_{channel_id}.jsonl'
            else:
                file_path = f'conversations/{guild_id}_{channel_id}.jsonl'

            # Prepare the full conversation history including the system prompt
            full_history = [{"role": "system", "content": system_prompt}] + history

            # Write the entire conversation history as a single JSON object with a "messages" array
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump({"messages": full_history}, f, ensure_ascii=False)

    @commands.command(name='grilledcheese_help', aliases=['grilledcheese_commands', 'grilledcheesehelp'])
    async def grilledcheese_help(self, ctx):
        """Displays the help message with a list of available commands."""
        embed = discord.Embed(
            title="AI Grilled Cheese Help",
            description="Here are the commands you can use with AI Grilled Cheese:",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="General Commands",
            value=(
                "**g!grilledcheese_help**\n"
                "Displays this help message.\n\n"
                "**g!set_reaction_threshold <percentage>**\n"
                "Sets the reaction threshold (0-100%). Determines how often AI Grilled Cheese reacts to messages with emojis.\n\n"
                "**g!set_reply_threshold <percentage>**\n"
                "Sets the reply threshold (0-100%). Determines how often AI Grilled Cheese randomly replies to messages.\n"
            ),
            inline=False
        )
        embed.add_field(
            name="Interaction with AI Grilled Cheese",
            value=(
                "AI Grilled Cheese will respond to messages that mention it or contain trigger words.\n"
                "It may also randomly reply or react to messages based on the set thresholds.\n"
                "To get AI Grilled Cheese's attention, you can mention it or use one of its trigger words.\n"
            ),
            inline=False
        )
        embed.add_field(
            name="Examples",
            value=(
                "- **Mentioning AI Grilled Cheese:** `@GrilledCheeseBot How are you today?`\n"
                "- **Using a trigger word:** `Grilled Cheese, tell me a joke!`\n"
                "- **Setting reaction threshold:** `g!set_reaction_threshold 50`\n"
                "- **Setting reply threshold:** `g!set_reply_threshold 20`\n"
            ),
            inline=False
        )
        embed.set_footer(text="Feel free to reach out if you have any questions!")
        await ctx.send(embed=embed)

    @grilledcheese_help.error
    async def grilledcheese_help_error(self, ctx, error):
        logger.exception(f"Error in grilledcheese_help command: {error}")
        await ctx.send("An error occurred while displaying the help message.")

    @commands.command(name='set_reaction_threshold')
    async def set_reaction_threshold(self, ctx, percentage: float):
        """Set the reaction threshold (percentage of messages AI Grilled Cheese reacts to)."""
        if 0 <= percentage <= 100:
            reaction_probability = percentage / 100
            guild_id = ctx.guild.id if ctx.guild else 'DM'
            channel_id = ctx.channel.id
            reply_probability, _ = load_probabilities(guild_id, channel_id)
            save_probabilities(guild_id, channel_id, reply_probability, reaction_probability)
            await ctx.send(f"Reaction threshold set to {percentage}%")
        else:
            await ctx.send("Please enter a percentage between 0 and 100.")

    @set_reaction_threshold.error
    async def set_reaction_threshold_error(self, ctx, error):
        logger.exception(f"Error in set_reaction_threshold command: {error}")
        await ctx.send("Invalid input. Please enter a valid percentage between 0 and 100.")

    @commands.command(name='set_reply_threshold')
    async def set_reply_threshold(self, ctx, percentage: float):
        """Set the reply threshold (percentage of messages AI Grilled Cheese replies to)."""
        if 0 <= percentage <= 100:
            reply_probability = percentage / 100
            guild_id = ctx.guild.id if ctx.guild else 'DM'
            channel_id = ctx.channel.id
            _, reaction_probability = load_probabilities(guild_id, channel_id)
            save_probabilities(guild_id, channel_id, reply_probability, reaction_probability)
            await ctx.send(f"Reply threshold set to {percentage}%")
        else:
            await ctx.send("Please enter a percentage between 0 and 100.")

    @set_reply_threshold.error
    async def set_reply_threshold_error(self, ctx, error):
        logger.exception(f"Error in set_reply_threshold command: {error}")
        await ctx.send("Invalid input. Please enter a valid percentage between 0 and 100.")


def setup(bot):
    bot.add_cog(GrilledCheeseCog(bot))
