# Discord Message Bot

A private Discord control panel for composing, previewing, publishing, and managing bot messages. The same configured owner can use it in every server where the bot is installed when commands are registered globally.

## 1. Set up the Discord application

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and choose **New Application**. Give it a name.
2. On the **Bot** page, choose **Reset Token** to reveal and copy the bot token. Keep it private. Leave the privileged gateway intents off.
3. In Discord, open **User Settings → Advanced** and enable **Developer Mode**. Right-click your own profile and select **Copy User ID**. Use this number for `OWNER_ID`.
4. Optional for single-server testing. Right-click your server icon, select **Copy Server ID**, and use that number for `GUILD_ID`. Leave `GUILD_ID` empty for global registration across all installed servers.
5. In the application's **Installation** page, enable **Guild Install**. Set its scopes to `bot` and `applications.commands`. Under bot permissions choose **View Channels**, **Send Messages**, **Embed Links**, **Attach Files**, and **Read Message History**. Copy the installation link, open it, and add the bot to your server. You need permission to install server apps.
6. Check any channel or category overrides for the bot. Grant **View Channel** and **Send Messages** wherever you want it to post, **Embed Links** for custom embeds, **Attach Files** for uploads, and **Read Message History** where you want to edit or delete past bot messages. The bot can post into text and announcement channels. Publishing an announcement to follower servers is a separate Discord action.

## 2. Host on Railway

1. Push the files in this directory to a GitHub repository. Keep the project's files at the repository root. If you put them in a subfolder such as `/discord-message-bot`, set the Railway service **Root Directory** to that folder and **Railway Config File** to `/discord-message-bot/railway.toml`. The project ignores local `.env` files.
2. In Railway, create a project using **Deploy from GitHub Repo**, or add the repo as a new service in an existing project.
3. In the service's **Variables** tab, set `DISCORD_TOKEN` to the application's bot token and `OWNER_ID` to your Discord user ID. Set `GUILD_ID` only for a single-server command registration. If Railway started a deploy before the variables were set, deploy again after saving them.
4. Railway uses Railpack and Python 3.12, installs `requirements.txt`, and starts `python -u bot.py` from `railway.toml`. Keep one replica. The bot connects outward to the Discord Gateway and runs as a worker. A public domain, port, HTTP health check, database, and persistent volume are unnecessary.
5. Open deployment logs. Look for `Synced 7 slash commands` and `Connected as bot ID`, then open Discord and run `/panel`. Guild commands normally appear quickly. Global registration may take longer to appear in clients. When moving from guild to global registration, Discord can retain old guild copies. Both scopes still enforce `OWNER_ID`.

To deploy from this directory with the [Railway CLI](https://docs.railway.com/cli), use `railway login`, `railway link` for your existing project, select the service if prompted, configure the same variables in its dashboard, then run `railway up --detach`.

## 3. Run locally on Windows

Install Python 3.12. Open PowerShell in this directory and run:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Use the bot token, your user ID, and optionally the server ID from Step 1. Save the file, then start the bot:

```powershell
.\.venv\Scripts\python.exe -u bot.py
```

The environment variables set by a host take precedence over values from `.env`. Use one running instance per bot token, including local and hosted instances.

## 4. Use the private control panel

1. Run **/panel** in your Discord server. The bot responds with a panel visible only to you. All commands and interactive actions check the configured user ID.
2. Click **Select Channel**. The **Sendable channels** dropdown lists destinations where the bot has **View Channel** and **Send Messages**, with a page for every 25 results. The native Discord picker offers search and filters by channel type. The bot checks its posting permissions for any selection from either dropdown and again before publishing.
3. Choose **Normal Message** and then **Write Text & Attach Files**, or use **Create Embed**. You can combine text, files, and embeds in one post. Text supports Discord Markdown and emoji. Upload images directly in the text modal. User and role notifications are off by default and can be enabled per send. Discord still applies its own mention permissions. Everyone and here notifications are disabled.
4. In the embed builder, choose the property to change, submit the modal, and repeat. **Edit Title** includes the title URL. **Edit Author** and **Edit Footer** include icons. **Set Image** and **Set Thumbnail** use public HTTP(S) image URLs. **Manage Fields** lets you edit or remove a field. Use **Add Embed** and the embed dropdown for multiple cards. Discord allows 10 embeds, 25 fields per embed, and 6,000 combined embed text characters per message.
5. Click **Preview Message**. Check the draft and the destination channel shown above the confirmation controls. Choose **Confirm Send** to post publicly there, **Select Channel** to change the destination and preview again, or **Cancel** to return to the draft. Selecting a channel or saving a modal does not publish anything.
6. The private receipt links to the published message. **Send Again** keeps the draft and asks for a destination, a new preview, and a new confirmation. **Edit Message** loads the posted message, and **Confirm Edit** saves changes in place. **Delete Message** requires a separate confirmation.

`/send` and `/embed` open the related editor. `/edit` and `/delete` take a message link or a message ID plus an optional channel. An ID uses the invoking channel by default. Both actions verify that the target was sent by this bot. `/status` reports gateway latency, and `/help` lists the commands.

Panels expire after 10 minutes of inactivity. Drafts and panel state are in memory, so a process restart closes them. Published messages remain in Discord and can still be managed by link or ID after a restart. Discord applies its channel upload limit and allows up to 10 attachments per message. This bot allows up to 24 MiB of combined file data per upload so the multipart request fits within Discord's request limit.
