# Qubot
「Qubit」用のDiscordボット

スラッシュコマンドと `q!` プレフィックスに対応したDiscordボットです。すべての出力は英語と日本語のバイリンガルEmbed（カラー `#AA64FF`）で表示されます。

## セットアップ
1. `pip install -r requirements.txt` を実行します。
2. `.env.example` を `.env` にコピーし、`DISCORD_TOKEN` を設定します。
3. Discord Developer Portalで **Message Content Intent** を有効にします（`q!` に必要です）。
4. `python bot.py` を実行します。

## コマンドの追加
`cogs/yourthing.py` を作成し、Cogと `setup(bot)` 関数を定義してください（`cogs/ping.py` を参照）。自動的に読み込まれます。
`commands.hybrid_command` を使うと `/name` と `q!name` の両方で動作します。返信には `core.embeds.make_embed(en, ja)` を使用してください。

## 権限
権限はユーザーIDの固定リストではなく、実行したユーザーのDiscord上のロールと権限を確認して判定します。
`.env` に設定する項目はありません。コマンドごとに `requires` で条件を指定します。

```python
from core.permissions import requires

@commands.hybrid_command(name="purge")
@requires(manage_messages=True)
async def purge(self, ctx, ...): ...

@commands.hybrid_command(name="announce")
@requires(roles=["Staff", 123456789012345678])
async def announce(self, ctx, ...): ...

@commands.hybrid_command(name="lock")
@requires(manage_channels=True, roles=["Moderator"])
async def lock(self, ctx, ...): ...
```

- キーワード引数（`manage_messages=True` など）は discord.py の権限名で、**すべて**満たす必要があります。チャンネルごとの権限上書きも考慮されます。
- `roles` にはロール名（大文字小文字を区別しない）またはロールIDを指定でき、**いずれか1つ**を持っていれば通過します。
- 権限とロールの両方を指定した場合は、両方を満たす必要があります。
- サーバーのオーナーは常に通過します。管理者（Administrator）権限を持つユーザーはすべての権限条件を満たしますが、`roles` の条件は別途必要です。
- DMでは使用できません。条件を満たさないユーザーには、バイリンガルの「権限がありません」Embedが表示されます（スラッシュコマンドの場合は本人にのみ表示されます）。
