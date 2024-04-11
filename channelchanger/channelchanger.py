discord.client: Ignoring exception in on_voice_state_update
Traceback (most recent call last):
  File "/data/venv/lib/python3.11/site-packages/discord/client.py", line 441, in _run_event
    await coro(*args, **kwargs)
  File "/data/cogs/CogManager/cogs/channelchanger/channelchanger.py", line 129, in on_voice_state_update
    await self.scan_one(self, before.channel)
  File "/data/cogs/CogManager/cogs/channelchanger/channelchanger.py", line 104, in scan_one
    channelConfig = await self.config.guild(ctx.guild).channels[channel.id]
                                            ^^^^^^^^^
AttributeError: 'ChannelChanger' object has no attribute 'guild'
