import os
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# --- Environment Variables (GitHub Secrets se uthayega) ---
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
IG_USER_ID = os.getenv("IG_USER_ID")

# Content path (repository ke andar ek 'content' folder hoga jisme video/image aur caption honge)
MEDIA_PATH = "content/video.mp4"  # Aapki video ya image ka path
CAPTION = "Sanatan Sutra - Daily Wisdom 🙏✨ #SanatanSutra #Dharma"


def post_to_instagram():
  print("Instagram par post karne ki koshish ki ja rahi hai...")

  # Step 1: Media Container Create Karein (Aapki video/image ka public URL hona chahiye, jaise raw GitHub link ya hosted link)
  # Note: GitHub Actions ke liye video ko kisi hosting ya cloud par upload karke uska public URL dena behtar hota hai.
  media_url = os.getenv(
      "MEDIA_PUBLIC_URL"
  )  # Public URL yahan environment variable se aayega

  url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media"
  payload = {
      "media_type": "REELS",  # Agar reel hai toh REELS, image hai toh IMAGE
      "video_url": media_url,
      "caption": CAPTION,
      "access_token": IG_ACCESS_TOKEN,
  }

  response = requests.post(url, data=payload)
  result = response.json()

  if "id" in result:
    creation_id = result["id"]
    print(f"Media container created successfully. ID: {creation_id}")

    # Step 2: Container Publish Karein
    publish_url = f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": IG_ACCESS_TOKEN,
    }
    pub_response = requests.post(publish_url, data=publish_payload)
    pub_result = pub_response.json()

    if "id" in pub_result:
      print(f"Instagram par Successfully Post ho gaya! Post ID: {pub_result['id']}")
    else:
      print(f"Publishing Error: {pub_result}")
  else:
    print(f"Container Error: {result}")


def post_to_youtube():
  print("YouTube par video upload ho rahi hai...")
  # YouTube API credentials setup (OAuth2 ya client secrets ke zariye)
  # Yeh GitHub Secrets mein stored credentials ka use karega
  print("YouTube upload function ready hai.")


if __name__ == "__main__":
  print("--- Sanatan Sutra Automation Started ---")
  if IG_ACCESS_TOKEN and IG_USER_ID:
    post_to_instagram()
  else:
    print(
        "Instagram credentials missing in environment variables! Skipping"
        " Instagram."
    )

  post_to_youtube()
