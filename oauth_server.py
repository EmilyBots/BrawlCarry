from flask import Flask, redirect, request, jsonify
import requests, sqlite3, os

app    = Flask(__name__)
DB     = "brawl.db"

CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("OAUTH_REDIRECT_URI")  # e.g. https://yourdomain.com/callback
BACKUP_GUILD  = os.getenv("BACKUP_GUILD_ID")
BOT_TOKEN     = os.getenv("DISCORD_TOKEN")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@app.route("/authorize")
def authorize():
    return redirect(
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}"
        f"&response_type=code&scope=identify%20guilds.join"
    )

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "Missing code", 400

    token_resp = requests.post("https://discord.com/api/oauth2/token", data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "authorization_code",
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})

    tokens = token_resp.json()
    access_token  = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    if not access_token:
        return "OAuth failed", 400

    user_resp = requests.get("https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"})
    user = user_resp.json()
    user_id = int(user["id"])

    conn = get_db()
    c    = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS oauth_users (
        user_id INT PRIMARY KEY,
        access_token TEXT,
        refresh_token TEXT
    )""")
    c.execute("INSERT OR REPLACE INTO oauth_users (user_id, access_token, refresh_token) VALUES (?, ?, ?)",
              (user_id, access_token, refresh_token))
    conn.commit()
    conn.close()

    return "<h2>✅ Backup access secured! You may close this tab.</h2>"

@app.route("/restore_all")
def restore_all():
    secret = request.args.get("secret")
    if secret != os.getenv("RESTORE_SECRET"):
        return "Unauthorized", 403

    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT * FROM oauth_users")
    users = c.fetchall()
    conn.close()

    results = {"success": 0, "failed": 0}
    for user in users:
        resp = requests.put(
            f"https://discord.com/api/guilds/{BACKUP_GUILD}/members/{user['user_id']}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            json={"access_token": user["access_token"]}
        )
        if resp.status_code in (200, 201, 204):
            results["success"] += 1
        else:
            results["failed"] += 1

    return jsonify(results)

if __name__ == "__main__":
    app.run(port=5000)
