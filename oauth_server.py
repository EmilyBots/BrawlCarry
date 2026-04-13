from flask import Flask, redirect, request, jsonify
import requests, sqlite3, os

app = Flask(__name__)
DB = "brawl.db"

CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("OAUTH_REDIRECT_URI")
BOT_TOKEN     = os.getenv("DISCORD_TOKEN")
RESTORE_SECRET = os.getenv("RESTORE_SECRET")

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_oauth_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS oauth_users (
        user_id INTEGER PRIMARY KEY,
        access_token TEXT,
        refresh_token TEXT
    )""")
    conn.commit()
    conn.close()

init_oauth_db()

def refresh_token_for_user(user):
    resp = requests.post("https://discord.com/api/oauth2/token", data={
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "refresh_token",
        "refresh_token": user["refresh_token"],
    }, headers={"Content-Type": "application/x-www-form-urlencoded"})
    tokens = resp.json()
    if "access_token" in tokens:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "UPDATE oauth_users SET access_token = ?, refresh_token = ? WHERE user_id = ?",
            (tokens["access_token"], tokens["refresh_token"], user["user_id"])
        )
        conn.commit()
        conn.close()
        return tokens["access_token"]
    return None

@app.route("/authorize")
def authorize():
    return redirect(
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds.join"
    )

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return "<h2>❌ Authorization failed. Missing code.</h2>", 400

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
        return "<h2>❌ OAuth failed. Please try again.</h2>", 400

    user_resp = requests.get(
        "https://discord.com/api/users/@me",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    user = user_resp.json()
    user_id = int(user["id"])

    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT OR REPLACE INTO oauth_users (user_id, access_token, refresh_token) VALUES (?, ?, ?)",
        (user_id, access_token, refresh_token)
    )
    conn.commit()
    conn.close()

    return """
    <html>
    <body style='background:#0A0E1A;display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;'>
    <div style='text-align:center;color:white;'>
        <h1 style='color:#2ECC71;font-size:48px;'>✅</h1>
        <h2>Backup Access Secured!</h2>
        <p style='color:#aaa;'>You will automatically be added to the backup server if needed.<br>You may close this tab.</p>
    </div>
    </body>
    </html>
    """

@app.route("/restore", methods=["POST"])
def restore():
    secret      = request.json.get("secret")
    backup_guild = request.json.get("guild_id")

    if secret != RESTORE_SECRET:
        return jsonify({"error": "Unauthorized"}), 403
    if not backup_guild:
        return jsonify({"error": "Missing guild_id"}), 400

    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT * FROM oauth_users")
    users = c.fetchall()
    conn.close()

    results = {"success": 0, "failed": 0, "refreshed": 0}

    for user in users:
        access_token = user["access_token"]
        resp = requests.put(
            f"https://discord.com/api/guilds/{backup_guild}/members/{user['user_id']}",
            headers={"Authorization": f"Bot {BOT_TOKEN}"},
            json={"access_token": access_token}
        )
        if resp.status_code == 401:
            # Token expired — try refresh
            new_token = refresh_token_for_user(user)
            if new_token:
                results["refreshed"] += 1
                resp = requests.put(
                    f"https://discord.com/api/guilds/{backup_guild}/members/{user['user_id']}",
                    headers={"Authorization": f"Bot {BOT_TOKEN}"},
                    json={"access_token": new_token}
                )
        if resp.status_code in (200, 201, 204):
            results["success"] += 1
        elif resp.status_code != 401:
            results["failed"] += 1

    return jsonify(results)

@app.route("/count")
def count():
    conn = get_db()
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM oauth_users")
    cnt = c.fetchone()["cnt"]
    conn.close()
    return jsonify({"authorized_users": cnt})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
