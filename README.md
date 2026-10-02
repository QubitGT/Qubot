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

## バックエンド連携
`.env` の `MASUTA_API` にバックエンドのURL、`HIMITSU_KAGI` に管理者キーを設定します。

## コンソールコマンド
管理者権限（Administrator）が必要です。

- `q!console add <ID> [名前]` / `/console add`: バックエンドにIDを追加します。名前を省略するとコマンド実行者の表示名が使われます。
- `q!console del <ID> [ID ...]` / `/console del`: IDを削除します。スペース区切りで複数指定できます。`q!console remove` でも動作します。

## バックエンドコマンド
`.env` の `BOT_ADMINISTRATION` に記載したユーザーID（カンマ区切り）のみ使用できます。

- `q!backend serverdata`（JSONファイルを添付）/ `/backend serverdata`: 添付したファイルでバックエンドの `serverdata.json` を丸ごと置き換えます。
- `q!backend restart` / `/backend restart`: ボットを再起動します。

## リアクションロール
`ManageMessages` と `ManageRoles` の両方の権限が必要です。設定は `data/reactionroles.db`（SQLite）に保存され、再起動後も維持されます。

- `/reactionrole add <emoji> <role> <type> <message-link>`: メッセージにリアクションロールを追加します。
- `/reactionrole remove <reaction-id>`: リアクションロールを削除します。
- `/reactionrole list`: このサーバーのリアクションロールを一覧表示します。

タイプ: `normal`（リアクションで付与、解除で剥奪）、`unique`（そのメッセージからは1つのみ）、`verify`（付与のみ、解除しても保持）、`drop`（リアクションで剥奪）。
自分の最上位ロール以上のロールは設定できません。ロールに特別な権限（メッセージの管理など）がある場合は確認が表示されます。

## 認証
`.env` の `VERIFY_CHANNEL` のチャンネルに認証メッセージを自動で投稿します（既に存在する場合は再投稿しません。削除された場合は再投稿します）。
メッセージのボタンを押すと画像認証（キャプチャ）が表示され、正しい文字を入力すると `VERIFY_ROLE` のロールが付与されます。認証結果は本人にのみ表示されます。
ボットのロールは `VERIFY_ROLE` より上位にあり、ロールの管理権限が必要です。

## ハニーポット
`.env` の `HONEYPOT_CHANNEL_ID` のチャンネルにボット以外がメッセージを送信すると、そのメッセージを削除し、本人にDMで通知してからサーバーからキックします（DMが無効でもキックします）。1時間ごとにチャンネルを確認し、残っているメッセージも同様に処理します。
ボットには「メンバーをキック」と「メッセージの管理」の権限が必要です。
