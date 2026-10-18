import os
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def upload_short():
    print("🚀 Preparing to upload video to YouTube...")
    
    client_id = os.environ.get("YT_CLIENT_ID")
    client_secret = os.environ.get("YT_CLIENT_SECRET")
    refresh_token = os.environ.get("YT_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print("⚠️ YouTube credentials missing in GitHub Secrets! Skipping upload.")
        return

    with open("video_metadata.json", "r") as f:
        meta = json.load(f)

    title = meta.get("title", "Creepy Mystery You Should Know #shorts")[:100]
    description = meta.get("description", "Watch till the end...") + "\n\n#shorts #mystery #thriller #creepy #storytime"

    creds = Credentials(
        None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"]
    )

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["shorts", "mystery", "creepy", "thriller", "scary", "facts"],
            "categoryId": "24"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload("final_short.mp4", chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    response = request.execute()
    print(f"✅ Successfully Uploaded to YouTube! Video ID: {response['id']}")
    print(f"🔗 Watch here: https://youtube.com/shorts/{response['id']}")

if __name__ == "__main__":
    upload_short()
