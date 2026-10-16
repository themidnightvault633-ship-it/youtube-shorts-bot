import os
import json
import random
import time
import wave
import textwrap
import requests
import numpy as np
from google import genai
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from io import BytesIO
from moviepy.editor import ImageClip, AudioFileClip, CompositeAudioClip, concatenate_videoclips

if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

api_key = os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

# Built-in High-Retention Viral Thriller Stories (Used if API is busy, or as rotating library)
VIRAL_STORIES = [
    {
        "title": "Someone Sent Me A Photo Of Myself Sleeping... From Inside My Room #shorts",
        "description": "I live alone on the 14th floor, and my door was locked from the inside...",
        "character_style": "A 22-year-old young man with messy dark hair wearing a dark grey hoodie, cinematic 3D Unreal Engine 5 thriller animation style, dramatic neon blue and warm amber lighting, expressive face, 8k resolution",
        "segments": [
            {
                "narration": "At 2:47 AM, my phone buzzed with an AirDrop request from a device named 'Right Behind You'.",
                "visual": "sitting in bed in a dark apartment looking down at a brightly glowing smartphone screen with a shocked expression, neon blue lighting"
            },
            {
                "narration": "Thinking it was a prank from my neighbor, I clicked accept—and my blood instantly turned to ice.",
                "visual": "extreme close up of terrified wide eyes illuminated by the bright glow of a phone screen in a dark bedroom, sweat on forehead"
            },
            {
                "narration": "It was a high-definition photo of me lying in my bed, taken from the corner of my own ceiling just ten seconds ago.",
                "visual": "high angle POV shot looking down from the ceiling corner at the young man sitting on his bed in a dimly lit apartment bedroom"
            },
            {
                "narration": "I live alone on the fourteenth floor, and my front door was deadbolted from the inside.",
                "visual": "standing up slowly in the bedroom looking towards a heavy locked apartment door with a metal chain lock, tense dramatic shadows"
            },
            {
                "narration": "With my hands shaking, I turned on my phone's flashlight and slowly pointed it toward the open closet door.",
                "visual": "holding up a glowing smartphone flashlight beam cutting through the dark room towards a slightly open wooden closet door"
            },
            {
                "narration": "The closet was empty, Lock screen lit up with a new message: 'Wrong place to look, check under the bed.'",
                "visual": "two glowing pale eyes staring out from the pitch black gap underneath the bed frame while the boy's feet stand right next to the bed"
            }
        ]
    },
    {
        "title": "Why You Should Never Answer A Call From Your Own Number #shorts",
        "description": "The voice on the other end sounded exactly like me, screaming a warning...",
        "character_style": "A 22-year-old young man with sharp features wearing a red and black jacket, 3D Pixar and Unreal Engine 5 thriller animation style, volumetric cinematic lighting, sharp focus, 8k",
        "segments": [
            {
                "narration": "Two nights ago, my phone started ringing at 3 AM, and the caller ID showed my own name and number.",
                "visual": "standing in a modern kitchen at night holding a ringing smartphone showing an incoming call, dramatic blue moonlight through window"
            },
            {
                "narration": "Every instinct told me to decline it, but curiosity got the better of me and I pressed answer.",
                "visual": "holding the smartphone up to his ear with a tense nervous expression, warm kitchen lamp illuminating half of his face"
            },
            {
                "narration": "Through heavy static, I heard my own voice crying in panic, whispering: 'Do not open the front door at 3:05.'",
                "visual": "wide-eyed horrified reaction while listening to the phone, dark shadows stretching across the wall behind him"
            },
            {
                "narration": "Before I could speak, the line went dead, and the digital clock on my microwave clicked to 3:05 AM.",
                "visual": "looking at a glowing green digital clock on a kitchen microwave showing 3:05 in a dark eerie room"
            },
            {
                "narration": "Suddenly, three loud, desperate knocks echoed from my front door, and someone outside yelled my name in my exact voice.",
                "visual": "standing frozen in the hallway staring at the wooden front door as dust shakes off the frame from a heavy knock"
            },
            {
                "narration": "When I looked through the peephole, I saw myself standing in the hallway—covered in rain, begging to be let in before 'it' found me.",
                "visual": "fisheye peephole view showing an identical twin of the young man outside in a dark corridor looking terrified behind his shoulder"
            }
        ]
    }
]

def generate_story():
    print("🧠 Crafting High-Retention Thriller Story with Gemini...")
    prompt = """
    Write an ultra-engaging, fast-paced 45-second psychological thriller story for a YouTube Short.
    NO boring 'internet rules'. Write a first-person story ('I') with:
    1. Segment 1: An insane, immediate hook in the first 3 seconds (e.g., receiving a creepy photo, hearing a voice, finding a hidden room).
    2. Segments 2-5: Escalating tension and investigation.
    3. Segment 6: A mind-blowing, spine-chilling plot twist cliffhanger at the very last second.
    Each segment's 'visual' MUST describe a completely DIFFERENT camera angle and action so no two images look similar.
    Return ONLY a valid JSON object with no markdown, structured like this:
    {
      "title": "Viral Title #shorts",
      "description": "Creepy short description...",
      "character
