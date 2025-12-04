"""
OneDrive UI (Flask) — Full Web Interface
=======================================
This is a **pure Flask-based UI** for OneDrive (Microsoft Graph API).  
No CLI required — everything runs through a browser.

Features:
- Login via Device Code (interactive) OR App Credentials
- View files & folders
- Create folders
- Upload files
- Download files
- Delete items

Run:
  pip install flask msal requests python-dotenv
  python app.py
Then open:
  http://localhost:5000

Set environment variables in a .env file:
-----------------------------------------
For **Device Code** (OneDrive personal / delegated):
  AUTH_FLOW=device
  CLIENT_ID=your_client_id
  TENANT_ID=your_tenant_id

For **App-only** (server-to-server):
  AUTH_FLOW=app
  CLIENT_ID=your_client_id
  CLIENT_SECRET=your_client_secret
  TENANT_ID=your_tenant_id
  TARGET_USER=user@domain.com

"""
import tempfile
import os
import requests
import msal
from flask import Flask, render_template_string, request, redirect, send_file
from dotenv import load_dotenv

load_dotenv()

AUTH_FLOW = os.environ.get("AUTH_FLOW", "device").lower()
CLIENT_ID = os.environ.get("CLIENT_ID")
TENANT_ID = os.environ.get("TENANT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
TARGET_USER = os.environ.get("TARGET_USER")

GRAPH = "https://graph.microsoft.com/v1.0"

def get_msal_app():
    if AUTH_FLOW == "app":
        return msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{TENANT_ID}",
            client_credential=CLIENT_SECRET,
        )

    return msal.PublicClientApplication(
        CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{TENANT_ID}",
    )

token_cache = None

def get_token():
    global token_cache
    if token_cache:
        return token_cache

    app = get_msal_app()

    if AUTH_FLOW == "app":
        scope = ["https://graph.microsoft.com/.default"]
        result = app.acquire_token_for_client(scopes=scope)
        token_cache = result.get("access_token")
        return token_cache

    # Device Code Login
    flow = app.initiate_device_flow(scopes=["Files.ReadWrite.All", "User.Read", "offline_access"])
    print("==== DEVICE LOGIN ====")
    print(flow["message"])
    result = app.acquire_token_by_device_flow(flow)
    token_cache = result.get("access_token")
    return token_cache

def drive_prefix():
    if AUTH_FLOW == "app":
        return f"/users/{TARGET_USER}/drive"
    return "/me/drive"

# -------------------- Flask UI --------------------
app = Flask(__name__)

HTML = """
<h2>OneDrive Web UI</h2>
<a href='/'>Refresh</a><br><br>

<h3>Files</h3>
<ul>
{% for f in files %}
  <li>
    {{f.name}} — {% if f.folder %}Folder{% else %}File{% endif %}
    {% if not f.folder %}
      <a href='/download?path={{f.path}}'>Download</a>
    {% endif %}
    <a href='/delete?path={{f.path}}'>Delete</a>
  </li>
{% endfor %}
</ul>

<hr>
<h3>Upload File</h3>
<form action='/upload' method='post' enctype='multipart/form-data'>
  <input type='file' name='file'>
  Remote Path: <input name='remote'>
  <button>Upload</button>
</form>

<hr>
<h3>Create Folder</h3>
<form action='/mkdir' method='post'>
  New Folder Path: <input name='path'>
  <button>Create Folder</button>
</form>
"""

# -------------------- Actions --------------------
@app.route("/")
def index():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    url = GRAPH + f"{drive_prefix()}/root/children"
    r = requests.get(url, headers=headers)
    items = r.json().get("value", [])

    files = []
    for it in items:
        files.append(type("File", (), {
            "name": it.get("name"),
            "folder": it.get("folder"),
            "path": f"/{it.get('name')}"
        }))

    return render_template_string(HTML, files=files)

@app.route("/upload", methods=["POST"])
def upload():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    file = request.files["file"]
    remote = request.form["remote"]

    url = GRAPH + f"{drive_prefix()}/root:{remote}:/content"
    r = requests.put(url, headers=headers, data=file.read())

    return redirect("/")

@app.route("/mkdir", methods=["POST"])
def mkdir():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    path = request.form["path"].rstrip("/")

    parent, _, name = path.rpartition("/")
    parent_path = parent if parent else None

    if parent_path:
        url = GRAPH + f"{drive_prefix()}/root:{parent_path}:/children"
    else:
        url = GRAPH + f"{drive_prefix()}/root/children"

    payload = {"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"}
    requests.post(url, headers=headers, json=payload)

    return redirect("/")

@app.route("/delete")
def delete():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    path = request.args.get("path")

    url = GRAPH + f"{drive_prefix()}/root:{path}:/"
    requests.delete(url, headers=headers)

    return redirect("/")

@app.route("/download")
def download():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    path = request.args.get("path")

    url = GRAPH + f"{drive_prefix()}/root:{path}:/content"
    r = requests.get(url, headers=headers)

    # Get system temp directory
    tmp_dir = tempfile.gettempdir()

    # Build full temp file path
    filename = os.path.basename(path)
    temp_path = os.path.join(tmp_dir, filename)

    # Save file
    with open(temp_path, "wb") as f:
        f.write(r.content)

    return send_file(temp_path, as_attachment=True)


if __name__ == "__main__":
    print("Running OneDrive Flask UI → http://localhost:5000")
    app.run(debug=True)
