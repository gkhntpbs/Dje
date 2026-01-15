import discord


class ShortcutsView(discord.ui.View):
    def __init__(self, shortcuts: list[tuple[str, str]], play_callback, timeout: float = 120.0) -> None:
        super().__init__(timeout=timeout)
        self._play_callback = play_callback
        self.message: discord.Message | None = None

        for name, _ in shortcuts:
            label = name[:80]
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
            button.callback = self._make_callback(name)
            self.add_item(button)

    def _make_callback(self, name: str):
        async def _callback(interaction: discord.Interaction) -> None:
            await self._play_callback(interaction, name)

        return _callback

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                return
