import os
import sys
import re
import glob
import html
import json
import time
import math
import shutil
import random
import asyncio
import logging
import argparse
import subprocess
import urllib.parse
import xml.etree.ElementTree as ET
from io import BytesIO
from datetime import datetime, timedelta, timezone

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("NewsBot")

# ================= 1. CREDENTIALS, CONFIG & TIME-OF-DAY EDITIONS =================
def _clean_secret(val):
    return (val or "").strip().strip('"').strip("'").strip()

GEMINI_API_KEY = _clean_secret(os.environ.get("GEMINI_API_KEY", ""))
YT_CLIENT_ID = _clean_secret(os.environ.get("YT_CLIENT_ID", ""))
YT_CLIENT_SECRET = _clean_secret(os.environ.get("YT_CLIENT_SECRET", ""))
YT_REFRESH_TOKEN = _clean_secret(os.environ.get("YT_REFRESH_TOKEN", ""))

CATEGORIES = ["NATION", "WORLD", "TECHNOLOGY"]
SHORTS_INTERVAL_HOURS = 3
ENABLE_LONG_VIDEOS = True
MIN_LONG_VIDEO_SECONDS = 605.0

EDITION_MORNING = "MORNING"
EDITION_AFTERNOON = "AFTERNOON"
EDITION_EVENING = "EVENING"

EDITION_CONFIGS = {
    EDITION_MORNING: {
        "target_count": 100,
        "title_prefix": "🔴 LIVE महाबुलेटिन: 24 घंटे की 100 बड़ी ख़बरें",
        "header_title": "24 घंटे की 100 बड़ी ख़बरें  |  TOP 100 SUPERFAST NEWS",
        "badge_label": "100 खबर",
        "counter_prefix": "ख़बर",
        "bulletin_label": "100 SUPERFAST",
        "speed_words": 14,
    },
    EDITION_AFTERNOON: {
        "target_count": 16,
        "title_prefix": "🔴 LIVE दोपहर महाबुलेटिन: आज की सबसे बड़ी व अहम ख़बरें",
        "header_title": "दोपहर महाबुलेटिन  |  SPECIAL IN-DEPTH PRIME-TIME REPORT",
        "badge_label": "बड़ी ख़बर",
        "counter_prefix": "बड़ी ख़बर",
        "bulletin_label": "दोपहर बुलेटिन",
        "speed_words": 75,
    },
    EDITION_EVENING: {
        "target_count": 50,
        "title_prefix": "🔴 LIVE शाम का महाबुलेटिन: दिनभर की Top 50 बड़ी ख़बरें",
        "header_title": "शाम का महाबुलेटिन  |  TOP 50 SUPERFAST HINDI NEWS",
        "badge_label": "TOP 50",
        "counter_prefix": "ख़बर",
        "bulletin_label": "TOP 50 NEWS",
        "speed_words": 26,
    },
}

def get_current_edition():
    try:
        utc_now = datetime.now(timezone.utc)
        ist_dt = utc_now + timedelta(hours=5, minutes=30)
        h = ist_dt.hour
        if 5 <= h < 12:
            return EDITION_MORNING
        elif 12 <= h < 17:
            return EDITION_AFTERNOON
        else:
            return EDITION_EVENING
    except Exception:
        return EDITION_MORNING

NEWS_FEEDS = {
    "NATION": [
        "https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi",
        "https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
        "https://www.amarujala.com/rss/breaking-news.xml",
        "https://ndtv.in/rss/top-stories",
    ],
    "TECHNOLOGY": [
        "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=hi&gl=IN&ceid=IN:hi",
        "https://news.google.com/rss/search?q=%E0%A4%9F%E0%A5%87%E0%A4%95%E0%A5%8D%E0%A4%A8%E0%A5%8B%E0%A4%B2%E0%A5%89%E0%A4%9C%E0%A5%80+OR+%E0%A4%8F%E0%A4%86%E0%A4%88&hl=hi&gl=IN&ceid=IN:hi",
        "https://feeds.bbci.co.uk/hindi/rss.xml",
    ],
    "WORLD": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.feedburner.com/ndtvnews-world-news",
        "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en",
    ],
}

VOICE_MAP = {
    "NATION": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
    "TECHNOLOGY": {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"},
    "WORLD": {"female": "en-US-JennyNeural", "male": "en-US-GuyNeural"},
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}

_ANCHOR_TOGGLE = 0
_FONT_CACHE = {}

def _ensure_system_fonts_on_ci():
    deva_path = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    if os.path.exists(deva_path) or not sys.platform.startswith("linux"):
        return
    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        try:
            logger.info("🔤 Installing Hindi Devanagari fonts on runner...")
            subprocess.run(["sudo", "apt-get", "update", "-y"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
            subprocess.run(["sudo", "apt-get", "install", "-y", "fonts-noto-core", "fonts-dejavu-core", "ffmpeg"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            _FONT_CACHE.clear()
        except Exception as e:
            logger.warning(f"Font auto-install warning: {e}")

def _pick_anchor_gender(override=None):
    global _ANCHOR_TOGGLE
    if override in ("male", "female"):
        return override
    gender = "female" if (_ANCHOR_TOGGLE % 2 == 0) else "male"
    _ANCHOR_TOGGLE += 1
    return gender

# ================= 2. CACHED BILINGUAL HINDI + ENGLISH FONT ENGINE =================
def _load_font_pair(size=36):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    deva_candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/lohit-devanagari/Lohit-Devanagari.ttf",
    ]
    latin_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    deva_font = next((ImageFont.truetype(p, size) for p in deva_candidates if os.path.exists(p)), None)
    latin_font = next((ImageFont.truetype(p, size) for p in latin_candidates if os.path.exists(p)), None)
    fallback = latin_font or deva_font or ImageFont.load_default()
    pair = ((deva_font or fallback), (latin_font or fallback))
    _FONT_CACHE[size] = pair
    return pair

def measure_bilingual_text(draw, text, size=34):
    if isinstance(draw, Image.Image):
        draw = ImageDraw.Draw(draw)
    deva_font, latin_font = _load_font_pair(size)
    clean = re.sub(r"[\U00010000-\U0010ffff]", "", str(text or ""))
    runs = re.findall(r"[\u0900-\u097F]+|[^\u0900-\u097F]+", clean)
    total_w = 0
    for run in runs:
        is_deva = bool(re.search(r"[\u0900-\u097F]", run))
        font = deva_font if is_deva else latin_font
        bbox = draw.textbbox((0, 0), run, font=font)
        total_w += max(0, bbox[2] - bbox[0])
    return total_w

def draw_bilingual_text(draw, xy, text, size=34, fill=(255, 255, 255)):
    if isinstance(draw, Image.Image):
        draw = ImageDraw.Draw(draw)
    deva_font, latin_font = _load_font_pair(size)
    clean = re.sub(r"[\U00010000-\U0010ffff]", "", str(text or ""))
    runs = re.findall(r"[\u0900-\u097F]+|[^\u0900-\u097F]+", clean)
    x, y = xy
    for run in runs:
        is_deva = bool(re.search(r"[\u0900-\u097F]", run))
        font = deva_font if is_deva else latin_font
        draw.text((x, y), run, fill=fill, font=font)
        bbox = draw.textbbox((x, y), run, font=font)
        x += max(0, bbox[2] - bbox[0])
    return x

def build_word_timings(narration, duration):
    words = [w for w in (narration or "").strip().split() if w]
    if not words:
        return [{"word": "", "start": 0.0, "end": duration, "idx": 0}]
    weights = []
    for w in words:
        pause_bonus = 2.4 if w.endswith(("।", ".", "!", "?", ":", ";")) else (1.1 if w.endswith(",") else 0.0)
        weights.append(max(1.5, len(w) * 0.85 + pause_bonus))
    total_wt = sum(weights)
    timings = []
    cur_t = 0.0
    usable_dur = max(0.5, duration - 0.15)
    for idx, (w, wt) in enumerate(zip(words, weights)):
        dt = (wt / total_wt) * usable_dur
        timings.append({"word": w, "start": cur_t, "end": cur_t + dt, "idx": idx})
        cur_t += dt
    timings[-1]["end"] = duration + 1.0
    return timings

# ================= 3. NEWS POOL & SCRIPT ENGINE =================
NATIONAL_STORIES = [
    {"title": "संसद के नए सत्र में डिजिटल सुरक्षा और नागरिक अधिकारों पर अहम चर्चा शुरू", "summary": "संसद के सत्र में डिजिटल सुरक्षा विधेयक पर विभिन्न दलों के नेताओं ने अपने महत्वपूर्ण सुझाव प्रस्तुत किए।", "category_tag": "राष्ट्रीय"},
    {"title": "देश के 100 नए शहरों में स्मार्ट अर्बन इलेक्ट्रिक ट्रांसपोर्ट प्रोजेक्ट को मंजूरी मिली", "summary": "केंद्र सरकार ने शहरी परिवहन को सुगम और पर्यावरण अनुकूल बनाने के लिए नए फंड की घोषणा की है।", "category_tag": "राष्ट्रीय"},
    {"title": "डिजिटल इंडिया मिशन: ग्रामीण पंचायतों में हाई-स्पीड ऑप्टिकल फाइबर नेटवर्क का विस्तार", "summary": "दूरदराज के ग्रामीण इलाकों में सरकारी सेवाएं और ऑनलाइन बैंकिंग अब सीधे इंटरनेट से जुड़ेंगी।", "category_tag": "राष्ट्रीय"},
    {"title": "राष्ट्रीय राजमार्ग नेटवर्क में 10 हजार किलोमीटर नए ग्रीन एक्सप्रेसवे का निर्माण तेज", "summary": "सड़क परिवहन मंत्रालय ने लॉजिस्टिक्स लागत घटाने के लिए नए इकोनॉमिक कॉरिडोर का काम तेज किया।", "category_tag": "राष्ट्रीय"},
    {"title": "सुप्रीम कोर्ट ने नागरिक सुविधाओं और त्वरित न्याय प्रणाली पर राज्यों को दिए निर्देश", "summary": "न्यायालय ने सभी राज्यों को ई-कोर्ट्स और डिजिटल जनसेवाओं की गुणवत्ता सुनिश्चित करने के निर्देश दिए।", "category_tag": "राष्ट्रीय"},
    {"title": "प्रधानमंत्री आवास योजना के तहत 20 लाख नए पक्के घरों के आवंटन को हरी झंडी", "summary": "ग्रामीण और शहरी दोनों क्षेत्रों में जरूरतमंद परिवारों को नए पक्के घर उपलब्ध कराने की प्रक्रिया शुरू।", "category_tag": "राष्ट्रीय"},
    {"title": "केंद्रीय कैबिनेट ने नई राष्ट्रीय रसद नीति के क्रियान्वयन की प्रगति की समीक्षा की", "summary": "औद्योगिक उत्पादन और व्यापार को बढ़ावा देने के लिए बंदरगाहों और रेल नेटवर्क को आपस में जोड़ा जा रहा है।", "category_tag": "राष्ट्रीय"},
    {"title": "देशभर के प्रमुख हवाई अड्डों पर डिजीयात्रा फेशियल रिकॉग्निशन तकनीक का विस्तार", "summary": "हवाई यात्रा को पेपरलेस और सुरक्षित बनाने के लिए नए टर्मिनल्स पर आधुनिक तकनीक स्थापित की गई।", "category_tag": "राष्ट्रीय"},
    {"title": "पूर्वोत्तर राज्यों में औद्योगिक निवेश और बुनियादी ढांचा विकास के लिए विशेष पैकेज", "summary": "पूर्वोत्तर भारत में पर्यटन, कनेक्टिविटी और स्थानीय रोजगार बढ़ाने के लिए नई योजनाएं प्रारंभ।", "category_tag": "राष्ट्रीय"},
    {"title": "राष्ट्रीय युवा कौशल विकास अभियान: 50 लाख युवाओं को आधुनिक उद्योग का प्रशिक्षण", "summary": "आर्टिफिशियल इंटेलिजेंस और रोबोटिक्स जैसे उभरते क्षेत्रों में युवाओं को रोजगार के अवसर दिए जाएंगे।", "category_tag": "राष्ट्रीय"},
    {"title": "इसरो ने अगले चंद्र अन्वेषण मिशन की तैयारियों का दूसरा महत्वपूर्ण चरण पूरा किया", "summary": "भारतीय अंतरिक्ष अनुसंधान संगठन ने उन्नत लैंडर और रोवर मॉड्यूल का सफल परीक्षण किया है।", "category_tag": "अंतरिक्ष"},
    {"title": "गगनयान मानव अंतरिक्ष मिशन के क्रू एस्केप सिस्टम का अंतिम सुरक्षा परीक्षण सफल", "summary": "भारतीय अंतरिक्ष यात्रियों की सुरक्षा सुनिश्चित करने वाले आपातकालीन सिस्टम का गहन परीक्षण पूरा हुआ।", "category_tag": "अंतरिक्ष"},
    {"title": "आदित्य एल-1 सौर वेधशाला ने सूर्य के चुंबकीय तूफानों का नया वैज्ञानिक डेटा भेजा", "summary": "वैज्ञानिकों को सौर ज्वालाओं और पृथ्वी के वायुमंडल पर उनके प्रभाव को समझने में अहम जानकारी मिली।", "category_tag": "अंतरिक्ष"},
    {"title": "भारतीय वायुसेना को मिला पहला स्वदेशी एलसीए तेजस एमके-1ए लड़ाकू विमान", "summary": "उन्नत रडार, इलेक्ट्रॉनिक वारफेयर सूट और लंबी दूरी की मिसाइलों से लैस तेजस वायुसेना में शामिल।", "category_tag": "रक्षा"},
    {"title": "नौसेना के स्वदेशी विमानवाहक पोत आईएनएस विक्रांत ने युद्धाभ्यास में दिखाया दम", "summary": "समुद्र में लड़ाकू विमानों की नाइट लैंडिंग और संयुक्त कॉम्बैट ऑपरेशंस का सफल अभ्यास किया गया।", "category_tag": "रक्षा"},
    {"title": "डीआरडीओ ने नई पीढ़ी की लंबी दूरी की प्रलय बैलिस्टिक मिसाइल का सफल परीक्षण किया", "summary": "सटीक मारक क्षमता और मोबाइल लॉन्चर से संचालित होने वाली इस मिसाइल ने सभी मानक पूरे किए।", "category_tag": "रक्षा"},
    {"title": "सीमा सुरक्षा बल ने पश्चिमी सीमाओं पर आधुनिक एंटी-ड्रोन सुरक्षा ग्रिड सक्रिय किया", "summary": "सीमा पार से घुसपैठ और तस्करी रोकने के लिए रडार और जैमर तकनीक को चौबीसों घंटे तैनात किया गया।", "category_tag": "रक्षा"},
    {"title": "भारतीय अर्थव्यवस्था ने चालू तिमाही में 7.6 प्रतिशत की मजबूत जीडीपी विकास दर दर्ज की", "summary": "विनिर्माण और सेवा क्षेत्र में उछाल के चलते भारत दुनिया की सबसे तेजी से बढ़ती अर्थव्यवस्था बना हुआ है।", "category_tag": "अर्थव्यवस्था"},
    {"title": "यूपीआई डिजिटल लेन-देन ने रचा इतिहास, एक महीने में 1500 करोड़ से अधिक ट्रांजेक्शन", "summary": "रिटेल और ऑनलाइन पेमेंट में भारत का स्वदेशी यूपीआई दुनिया भर में मॉडल के रूप में उभरा है।", "category_tag": "अर्थव्यवस्था"},
    {"title": "रिजर्व बैंक ने मौद्रिक नीति में महंगाई नियंत्रण और आर्थिक स्थिरता को प्राथमिकता दी", "summary": "आरबीआई गवर्नर ने कहा कि मजबूत बैंकिंग प्रणाली और विदेशी मुद्रा भंडार से अर्थव्यवस्था सुरक्षित है।", "category_tag": "अर्थव्यवस्था"},
    {"title": "भारत का विदेशी मुद्रा भंडार ऐतिहासिक उच्च स्तर 690 अरब डॉलर के पार पहुंचा", "summary": "मजबूत विदेशी निवेश और निर्यात में सुधार के कारण भारत का केंद्रीय बैंक भंडार रिकॉर्ड ऊंचाई पर है।", "category_tag": "अर्थव्यवस्था"},
    {"title": "जीएसटी राजस्व संग्रह में 12 प्रतिशत की वृद्धि, 1.85 लाख करोड़ रुपये का नया रिकॉर्ड", "summary": "व्यापारिक गतिविधियों में तेजी और टैक्स अनुपालन बेहतर होने से सरकारी खजाने को बड़ा बढ़ावा मिला।", "category_tag": "अर्थव्यवस्था"},
    {"title": "भारत में पहले वाणिज्यिक सेमीकंडक्टर फैब प्लांट का निर्माण कार्य रिकॉर्ड समय में शुरू", "summary": "अहमदाबाद और असम में बनने वाले इन प्लांट्स से भारत चिप निर्माण का वैश्विक केंद्र बनेगा।", "category_tag": "तकनीक"},
    {"title": "इंडिया एआई मिशन के तहत 10 हजार जीपीयू सुपरकंप्यूटिंग क्लस्टर की स्थापना का ऐलान", "summary": "भारतीय शोधकर्ताओं और स्टार्टअप्स को कृत्रिम बुद्धिमत्ता के मॉडल विकसित करने के लिए संसाधन मिलेंगे।", "category_tag": "तकनीक"},
    {"title": "टेलीकॉम विभाग ने भारत 6G विज़न के तहत 100 नए शोध पेटेंट और प्रोटोटाइप जारी किए", "summary": "अगली पीढ़ी की वायरलेस तकनीक में भारत अब मानक तय करने वाले अग्रणी देशों में शामिल हो गया है।", "category_tag": "तकनीक"},
    {"title": "भारतीय रेलवे ने 10 नई वंदे भारत स्लीपर और चेयर-कार ट्रेनों की रूपरेखा तय की", "summary": "लंबी दूरी की यात्रा को आरामदायक, सुरक्षित और तेज बनाने के लिए अत्याधुनिक स्लीपर ट्रेनें तैयार।", "category_tag": "रेलवे"},
    {"title": "मुंबई-अहमदाबाद बुलेट ट्रेन प्रोजेक्ट में 21 किमी लंबी अंडरसी सुरंग की खुदाई शुरू", "summary": "हाई-स्पीड रेल परियोजना के प्रमुख स्टेशन और ट्रैक बिछाने का काम युद्धस्तर पर जारी है।", "category_tag": "रेलवे"},
    {"title": "अमृत भारत स्टेशन योजना के तहत 500 से अधिक रेलवे स्टेशनों का पुनर्विकास शुरू", "summary": "यात्रियों को एयरपोर्ट जैसी विश्वस्तरीय सुविधाएं, रूफ प्लाजा और मल्टी-मॉडल कनेक्टिविटी मिलेगी।", "category_tag": "रेलवे"},
    {"title": "स्वदेशी ट्रेन टक्कर रोधी कवच प्रणाली का 5000 किलोमीटर ट्रैक पर इंस्टॉलेशन संपन्न", "summary": "ऑटोमैटिक ब्रेकिंग तकनीक से ट्रेनों के आमने-सामने टकराने का जोखिम पूरी तरह समाप्त हो जाएगा।", "category_tag": "रेलवे"},
    {"title": "गुजरात के खावड़ा में दुनिया का सबसे बड़ा 30 हजार मेगावाट रिन्यूएबल पार्क तैयार", "summary": "सोलर और विंड एनर्जी का यह महापरियोजना देश की ऊर्जा जरूरतों का बड़ा हिस्सा पूरा करेगी।", "category_tag": "पर्यावरण"},
    {"title": "पीएम सूर्य घर मुफ्त बिजली योजना: 1 करोड़ घरों की छतों पर सोलर पैनल का लक्ष्य", "summary": "आम उपभोक्ताओं को हर महीने 300 यूनिट मुफ्त बिजली और अतिरिक्त बिजली बेचने का अवसर मिला।", "category_tag": "पर्यावरण"},
    {"title": "इलेक्ट्रिक वाहनों की बिक्री में 40% वार्षिक वृद्धि, नेशनल हाईवे पर चार्जिंग हब तैयार", "summary": "राष्ट्रीय राजमार्गों पर हर 25 किलोमीटर पर फास्ट चार्जिंग स्टेशन्स स्थापित किए जा रहे हैं।", "category_tag": "पर्यावरण"},
    {"title": "पीएम किसान सम्मान निधि की 18वीं किस्त: 9 करोड़ किसानों के खातों में फंड ट्रांसफर", "summary": "प्रत्यक्ष लाभ अंतरण के माध्यम से बिना किसी बिचौलिए के सीधे किसानों को वित्तीय सहायता मिली।", "category_tag": "कृषि"},
    {"title": "प्राकृतिक और जैविक खेती के लिए राष्ट्रीय मिशन के तहत 10 लाख हेक्टेयर भूमि चिन्हित", "summary": "रासायनिक खादों से मुक्ति और मिट्टी की उर्वरता बढ़ाने के लिए किसानों को विशेष अनुदान उपलब्ध।", "category_tag": "कृषि"},
    {"title": "रबी फसलों के न्यूनतम समर्थन मूल्य (MSP) में केंद्र सरकार द्वारा उल्लेखनीय बढ़ोतरी", "summary": "गेहूं, सरसों और दलहन की खेती करने वाले किसानों को उत्पादन लागत पर 50% से अधिक लाभ सुनिश्चित।", "category_tag": "कृषि"},
    {"title": "आयुष्मान भारत योजना का विस्तार: 70 वर्ष से अधिक के सभी वरिष्ठ नागरिकों को स्वास्थ्य कवच", "summary": "वरिष्ठ नागरिकों को बिना किसी आय सीमा के मुफ्त और कैशलेस इलाज की ऐतिहासिक सुविधा मिली।", "category_tag": "स्वास्थ्य"},
    {"title": "देश में 100 नए मेडिकल कॉलेजों और सुपर-स्पेशियलिटी विंग्स को मिली मंजूरी", "summary": "ग्रामीण और दूरदराज के क्षेत्रों में डॉक्टरों की उपलब्धता और इलाज की सुविधाएं कई गुना बढ़ेंगी।", "category_tag": "स्वास्थ्य"},
    {"title": "स्वदेशी वैक्सीन और फार्मा निर्माण में भारत का नेतृत्व, 150 देशों को दवाओं का निर्यात", "summary": "किफायती और उच्च गुणवत्ता वाली दवाओं के उत्पादन में भारत 'विश्व की फार्मेसी' के रूप में स्थापित।", "category_tag": "स्वास्थ्य"},
    {"title": "राष्ट्रीय शिक्षा नीति: उच्च शिक्षण संस्थानों में कौशल आधारित नए पाठ्यक्रम लागू", "summary": "छात्रों को अपनी रुचि के अनुसार विषय चुनने और व्यावहारिक अनुभव प्राप्त करने की पूरी आजादी मिली।", "category_tag": "शिक्षा"},
    {"title": "खेलो इंडिया यूथ गेम्स में युवा एथलीटों ने राष्ट्रीय स्तर पर कई नए रिकॉर्ड बनाए", "summary": "ग्रासरूट स्तर से चयनित युवा खिलाड़ियों को ओलंपिक और एशियाई खेलों के लिए विशेष ट्रेनिंग दी जाएगी।", "category_tag": "खेल"},
    {"title": "विश्व टेस्ट चैंपियनशिप में भारतीय क्रिकेट टीम की जीत, अंक तालिका में शीर्ष स्थान", "summary": "गेंदबाजों और बल्लेबाजों के शानदार ऑलराउंड प्रदर्शन से टीम ने विदेशी टीम को कड़े मुकाबले में हराया।", "category_tag": "खेल"},
    {"title": "नीरज चोपड़ा ने डायमंड लीग फाइनल में शानदार प्रदर्शन कर देश का नाम रोशन किया", "summary": "भाला फेंक स्पर्धा में भारतीय स्टार ने दुनिया के शीर्ष एथलीटों को कड़ी टक्कर देकर पदक जीता।", "category_tag": "खेल"},
    {"title": "भारतीय महिला तीरंदाजी टीम ने विश्व कप चरण में स्वर्ण पदक जीतकर रचा इतिहास", "summary": "सटीक निशानेबाजी से भारतीय तीरंदाजों ने अंतरराष्ट्रीय मंच पर तिरंगा शान से लहराया।", "category_tag": "खेल"},
    {"title": "शतरंज ओलंपियाड में भारतीय ग्रैंडमास्टर्स का दबदबा, युवा सितारों का ऐतिहासिक प्रदर्शन", "summary": "भारतीय युवा ग्रैंडमास्टर्स ने विश्व के दिग्गज खिलाड़ियों को हराकर देश का मान बढ़ाया।", "category_tag": "खेल"},
    {"title": "राष्ट्रीय खेल विश्वविद्यालय में स्पोर्ट्स बायो-मैकेनिक्स सेंटर का भव्य उद्घाटन", "summary": "एथलीटों की फिटनेस, चोट से बचाव और डाइट प्लानिंग के लिए वैज्ञानिकों की टीम काम करेगी।", "category_tag": "खेल"},
    {"title": "केंद्रीय गृह मंत्रालय ने आपदा प्रबंधन बलों के लिए नए आधुनिक राहत उपकरण जारी किए", "summary": "बाढ़ और चक्रवात जैसी प्राकृतिक आपदाओं में त्वरित बचाव के लिए उन्नत बोट्स और ड्रोन्स तैनात।", "category_tag": "राष्ट्रीय"},
    {"title": "जल जीवन मिशन के तहत देश के 15 करोड़ से अधिक ग्रामीण परिवारों को नल से जल", "summary": "शुद्ध पेयजल पहुँचने से ग्रामीण क्षेत्रों में जल जनित बीमारियों में 60% की भारी कमी दर्ज।", "category_tag": "राष्ट्रीय"},
    {"title": "स्टार्टअप इंडिया में भारत बना दुनिया का तीसरा सबसे बड़ा यूनिकॉर्न हब", "summary": "डीप-टेक और फिनटेक स्टार्टअप्स में विदेशी निवेशकों ने रिकॉर्ड पूंजी का निवेश किया है।", "category_tag": "अर्थव्यवस्था"},
    {"title": "उत्पादन आधारित प्रोत्साहन (PLI) से मोबाइल व इलेक्ट्रॉनिक्स निर्यात में भारी उछाल", "summary": "भारत में बने स्मार्टफोन अब दुनिया के 80 से अधिक प्रमुख देशों में निर्यात हो रहे हैं।", "category_tag": "अर्थव्यवस्था"},
    {"title": "भारतीय मानक ब्यूरो (BIS) ने उपभोक्ता सुरक्षा के लिए 50 नए कड़े गुणवत्ता मानक लागू किए", "summary": "घरेलू उपकरणों और खिलौनों में गुणवत्ता सुनिश्चित कर उपभोक्ताओं के हितों की रक्षा की जाएगी।", "category_tag": "राष्ट्रीय"},
]

INTERNATIONAL_STORIES = [
    {"title": "संयुक्त राष्ट्र सुरक्षा परिषद में सुधारों पर वैश्विक सहमति, भारत की स्थायी सदस्यता को समर्थन", "summary": "वैश्विक मंच पर विकासशील देशों के समूह ने सुरक्षा परिषद के विस्तार की जोरदार वकालत की।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "भारत और यूरोपीय संघ के बीच मुक्त व्यापार समझौते (FTA) की बातचीत अंतिम पड़ाव में", "summary": "दोनों पक्षों के बीच टैरिफ घटाने और द्विपक्षीय व्यापार बढ़ाने पर सहमति बनने की संभावना तेज।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "क्वाड विदेश मंत्रियों की बैठक में इंडो-पैसिफिक क्षेत्र में समुद्री सुरक्षा पर साझा रणनीति तय", "summary": "समुद्री व्यापार मार्गों की स्वतंत्रता और साइबर सुरक्षा पर चारों देशों ने साझी प्रतिबद्धता दोहराई।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "भारत-मध्य पूर्व-यूरोप आर्थिक गलियारा (IMEC) के आधारभूत ढांचे पर अंतरराष्ट्रीय बैठक", "summary": "बंदरगाहों, रेलवे और डिजिटल केबल्स को आपस में जोड़ने वाले इस मेगा कॉरिडोर पर काम तेज।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अमेरिकी फेडरल रिजर्व ने मुद्रास्फीति और वैश्विक बाजार स्थिरता पर नई ब्याज दर नीति जारी की", "summary": "वैश्विक शेयर बाजारों और मुद्रा विनिमय पर अमेरिकी केंद्रीय बैंक के फैसले का व्यापक असर दिखा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "नासा के आर्टेमिस मिशन ने चंद्रमा की कक्षा में स्पेस स्टेशन 'गेटवे' की रूपरेखा फाइनल की", "summary": "मानव को दोबारा चंद्रमा पर उतारने और मंगल मिशन की तैयारी के लिए यह अंतरराष्ट्रीय स्टेशन बनेगा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "जेम्स वेब स्पेस टेलीस्कोप ने ब्रह्मांड के शुरुआती दौर की 5 नई आकाशगंगाओं की खोज की", "summary": "खगोलविदों ने 13 अरब वर्ष पुराने प्रकाश का अध्ययन कर तारों के निर्माण के रहस्य उजागर किए।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "वैश्विक एआई सुरक्षा शिखर सम्मेलन: 40 देशों ने जिम्मेदार आर्टिफिशियल इंटेलिजेंस पर हस्ताक्षर किए", "summary": "डीपफेक और स्वायत्त हथियारों के जोखिम को रोकने के लिए अंतरराष्ट्रीय निगरानी तंत्र पर सहमति बनी।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "मध्य पूर्व में शांति बहाली के लिए संयुक्त राष्ट्र और अरब देशों की आपातकालीन वार्ता संपन्न", "summary": "मानवीय सहायता आपूर्ति और युद्धविराम लागू करने के लिए अंतरराष्ट्रीय कूटनीतिक प्रयास तेज।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ओपेक प्लस देशों ने अंतरराष्ट्रीय तेल बाजार में कच्चे तेल उत्पादन कोटा पर फैसला लिया", "summary": "वैश्विक ऊर्जा कीमतों को स्थिर रखने के लिए प्रमुख तेल उत्पादक देशों ने आपूर्ति नीति की समीक्षा की।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ब्रिटेन और भारत के बीच द्विपक्षीय व्यापार साझेदारी में सर्विस और टेक सेक्टर को नई गति", "summary": "दोनों देशों के बीच पेशेवरों की आवाजाही और वित्तीय निवेश नियमों को सरल बनाया गया है।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "फ्रांस और भारत के बीच नागरिक परमाणु ऊर्जा और उन्नत एयरो-इंजन विकास पर नया समझौता", "summary": "लड़ाकू विमानों के लिए स्वदेशी जेट इंजन निर्माण में दोनों देशों के वैज्ञानिक मिलकर काम करेंगे।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "जापान ने सेमीकंडक्टर सप्लाई चेन को सुरक्षित करने के लिए भारत के साथ सहयोग बढ़ाया", "summary": "चिप डिजाइन और एडवांस्ड पैकेजिंग में दोनों देश एक-दूसरे के तकनीकी अनुभव का लाभ उठाएंगे।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "जर्मनी ने स्वच्छ ऊर्जा और ग्रीन हाइड्रोजन आयात के लिए भारतीय कंपनियों से साझेदारी की", "summary": "यूरोप की औद्योगिक जरूरतों को पूरा करने के लिए भारत से ग्रीन अमोनिया का निर्यात होगा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ब्रिक्स देशों के सम्मेलन में स्थानीय मुद्राओं में व्यापारिक भुगतान बढ़ाने पर सहमति बनी", "summary": "अंतरराष्ट्रीय वित्तीय लेन-देन में वैकल्पिक पेमेंट सिस्टम विकसित करने पर गहन चर्चा हुई।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "विश्व स्वास्थ्य संगठन ने नई वैश्विक महामारी रोकथाम और वैक्सीन वितरण संधि का ड्राफ्ट जारी किया", "summary": "गरीब और विकासशील देशों को भविष्य में दवाओं और टीकों की समान आपूर्ति सुनिश्चित की जाएगी।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ग्लोबल क्लाइमेट समिट: विकसित देशों ने ग्रीन क्लाइमेट फंड में 100 अरब डॉलर देने की पुष्टि की", "summary": "जलवायु परिवर्तन से प्रभावित द्वीपीय और अफ्रीकी देशों में आपदा राहत फंड बढ़ाया जाएगा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंतरराष्ट्रीय सौर गठबंधन (ISA) में 10 नए देश शामिल, अफ्रीका में 50 सौर परियोजनाएं शुरू", "summary": "दूरदराज के ग्रामीण इलाकों में सस्ती सौर बिजली पहुँचाने में भारतीय नेतृत्व की वैश्विक प्रशंसा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "विश्व बैंक की रिपोर्ट: भारत और दक्षिण एशिया वैश्विक आर्थिक वृद्धि का प्रमुख इंजन बने रहेंगे", "summary": "मजबूत घरेलू मांग और डिजिटल इंफ्रास्ट्रक्चर के चलते मंदी के दौर में भी विकास दर स्थिर।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंतरराष्ट्रीय मुद्रा कोष (IMF) ने वैश्विक ऋण संकट से निपटने के लिए नई राहत नीति का ऐलान किया", "summary": "कम आय वाले देशों के वित्तीय पुनर्गठन के लिए रियायती पैकेज की शर्तों में ढील दी गई है।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "लाल सागर और स्वेज नहर में वाणिज्यिक जहाजों की सुरक्षा के लिए बहुराष्ट्रीय नौसैनिक टास्क फोर्स तैनात", "summary": "वैश्विक समुद्री व्यापार को सुरक्षित रखने के लिए भारतीय नौसेना समेत कई देशों के युद्धपोत गश्त पर।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "सिंगापुर और भारत के बीच यूपीआई और पे-नाउ क्रॉस-बॉर्डर डिजिटल पेमेंट में भारी उछाल", "summary": "प्रवासी नागरिकों और छात्रों को न्यूनतम शुल्क पर तुरंत धन हस्तांतरण की सुविधा मिल रही है।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ऑस्ट्रेलिया ने भारतीय छात्रों और आईटी पेशेवरों के लिए वीजा नियमों में रियायतों की घोषणा की", "summary": "द्विपक्षीय संबंधों को प्रगाढ़ करते हुए दोनों देशों ने उच्च शिक्षा और शोध साझेदारी बढ़ाई।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "कनाडा और भारत के बीच व्यापारिक प्रतिनिधियों की बैठक, पोटाश और दालों के आयात पर चर्चा", "summary": "कृषि क्षेत्र की आपूर्ति श्रृंखला को सुचारू रखने के लिए दोनों पक्षों ने व्यापारिक चर्चा की।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "दक्षिण अफ्रीका में आयोजित जी20 शेरपा बैठक में खाद्य सुरक्षा और सतत विकास लक्ष्यों पर जोर", "summary": "विकासशील देशों के कर्ज राहत और तकनीकी हस्तांतरण के मुद्दों पर साझा सहमति बनी।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "रूस-चीन आर्थिक मंच: ऊर्जा आपूर्ति और यूरेशियन ट्रांसपोर्ट कॉरिडोर के विस्तार पर विचार", "summary": "प्राकृतिक गैस पाइपलाइन और उत्तरी समुद्री मार्ग से माल परिवहन की नई योजनाओं की समीक्षा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "यूरोपीय अंतरिक्ष एजेंसी ने बृहस्पति के बर्फीले चंद्रमाओं के अध्ययन के लिए 'जूस' मिशन का डेटा जारी किया", "summary": "उपग्रहों की बर्फीली सतह के नीचे गहरे महासागरों की मौजूदगी के पुख्ता संकेत मिले हैं।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "वैश्विक साइबर सुरक्षा रिपोर्ट: अंतरराष्ट्रीय रैंसमवेयर गिरोहों पर कानून प्रवर्तन एजेंसियों का शिकंजा", "summary": "इंटरपोल और सहयोगी देशों की पुलिस ने बहुराष्ट्रीय साइबर नेटवर्क को ध्वस्त कर संदिग्धों को पकड़ा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "विश्व व्यापार संगठन (WTO) में विकासशील देशों के कृषि सब्सिडी अधिकारों पर आम सहमति का प्रयास", "summary": "खाद्य सुरक्षा स्टॉकहोल्डिंग पर स्थायी समाधान खोजने के लिए जिनेवा में गहन विचार-विमर्श जारी।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "संयुक्त राष्ट्र मानवाधिकार परिषद ने शरणार्थी संकट और विस्थापन पर आपातकालीन बैठक बुलाई", "summary": "युद्ध और प्राकृतिक आपदाओं से विस्थापित करोड़ों नागरिकों के पुनर्वास और भोजन की व्यवस्था पर जोर।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "सऊदी अरब ने 'विज़न 2030' के तहत 500 अरब डॉलर के फ्यूचर सिटी प्रोजेक्ट 'नियोम' का काम तेज किया", "summary": "जीरो कार्बन और पूरी तरह रिन्यूएबल ऊर्जा से चलने वाले शहर के बुनियादी ढांचे का निर्माण जारी।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "संयुक्त अरब अमीरात ने अंतरराष्ट्रीय निवेशकों के लिए 10 वर्षीय गोल्डन वीजा नियमों को और आसान बनाया", "summary": "वैश्विक प्रतिभाओं और स्टार्टअप संस्थापकों को आकर्षित करने के लिए मध्य पूर्व का बड़ा फैसला।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "दक्षिण पूर्व एशियाई देशों (ASEAN) ने डिजिटल अर्थव्यवस्था फ्रेमवर्क समझौते पर हस्ताक्षर किए", "summary": "क्षेत्रीय ई-कॉमर्स और सीमा पार डेटा प्रवाह को बढ़ावा देने के लिए एकसमान नियम तय।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंतरराष्ट्रीय ऊर्जा एजेंसी (IEA): 2030 तक दुनिया भर में बिजली उत्पादन का आधा हिस्सा रिन्यूएबल से होगा", "summary": "कोयले और जीवाश्म ईंधन की जगह सोलर और विंड पावर के तेजी से अपनाने पर वैश्विक रिपोर्ट।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंटार्कटिका में वैज्ञानिकों ने 20 लाख वर्ष पुरानी बर्फ का कोर निकाल कर प्राचीन जलवायु का रहस्य खोला", "summary": "धरती के प्राचीन वायुमंडल में कार्बन डाइऑक्साइड के स्तर और तापमान के ऐतिहासिक बदलावों का पता चला।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ग्लोबल पासपोर्ट इंडेक्स: सिंगापुर और जापान शीर्ष पर, भारतीय पासपोर्ट की रैंकिंग में 5 पायदान का सुधार", "summary": "भारतीय नागरिकों को अब 62 देशों में वीजा-मुक्त या वीजा-ऑन-अराइवल की सुविधा उपलब्ध है।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "फीफा विश्व कप 2026 के लिए अमेरिका, कनाडा और मेक्सिको के 16 स्टेडियमों की तैयारी पूरी", "summary": "दुनिया के सबसे बड़े फुटबॉल टूर्नामेंट के लिए अत्याधुनिक इंफ्रास्ट्रक्चर और सुरक्षा प्लान तैयार।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "लंदन मैराथन में रिकॉर्ड 50 हजार से अधिक धावकों ने हिस्सा लेकर बनाया नया विश्व रिकॉर्ड", "summary": "दान और स्वास्थ्य जागरूकता के लिए आयोजित दौड़ में दुनिया भर के एथलीटों ने भाग लिया।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "यूनेस्को ने विश्व धरोहर सूची में 15 नए ऐतिहासिक स्थलों और सांस्कृतिक परंपराओं को शामिल किया", "summary": "प्राचीन वास्तुशिल्प और लुप्तप्राय लोककलाओं के संरक्षण के लिए अंतरराष्ट्रीय सहायता कोष जारी।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंतरराष्ट्रीय श्रम संगठन (ILO): वैश्विक कार्यबल में एआई टूल्स के इस्तेमाल से उत्पादकता में 25% का इजाफा", "summary": "कर्मचारियों के री-स्किलिंग और रोजगार सुरक्षा के लिए नई वैश्विक नीतियों की सिफारिश।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "तुर्किये और सीरिया में भूकंप पुनर्निर्माण: अंतरराष्ट्रीय मदद से 1 लाख नए घरों का निर्माण पूरा", "summary": "प्राकृतिक आपदा से तबाह क्षेत्रों में स्कूल, अस्पताल और बिजली-पानी की व्यवस्था बहाल।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "विश्व बौद्धिक संपदा संगठन (WIPO): भारत वैश्विक नवाचार सूचकांक में शीर्ष 40 देशों में शामिल", "summary": "पेटेंट आवेदनों, स्टार्टअप्स और शोध प्रकाशनों में अभूतपूर्व प्रगति से देश का वैश्विक मान बढ़ा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "स्विट्जरलैंड में ग्लेशियर पिघलने की दर पर नई रिपोर्ट, आल्प्स पर्वतों के जलस्रोतों पर चिंता", "summary": "यूरोपीय वैज्ञानिकों ने नदियों के जलस्तर और जलविद्युत परियोजनाओं पर असर का आकलन किया।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "ब्राजील के अमेजन वर्षावन में अवैध कटाई पर सख्त प्रतिबंध, वनों की कटाई में 50% की भारी कमी", "summary": "उपग्रह निगरानी और वन सुरक्षा दस्तों की सक्रियता से पृथ्वी के फेफड़े कहे जाने वाले जंगल सुरक्षित।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "दक्षिण कोरिया ने दुनिया की पहली वाणिज्यिक फ्लाइंग टैक्सी (eVTOL) सेवा के परीक्षण को मंजूरी दी", "summary": "शहरी ट्रैफिक जाम से मुक्ति दिलाने के लिए इलेक्ट्रिक एयर मोबिलिटी का 2026 में कमर्शियल लॉन्च होगा।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंतरराष्ट्रीय समुद्री संगठन (IMO): ग्रीन शिपिंग को बढ़ावा देने के लिए कार्बन टैक्स लगाने पर चर्चा", "summary": "वैश्विक मालवाहक जहाजों से ग्रीनहाउस गैस उत्सर्जन को 2050 तक शून्य करने का लक्ष्य निर्धारित।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "वैश्विक सेमीकंडक्टर अलायंस: ताइवान, अमेरिका और भारत मिलकर बनाएंगे नई चिप सप्लाई चेन", "summary": "भू-राजनीतिक तनावों के बीच महत्वपूर्ण तकनीकी घटकों की निर्बाध आपूर्ति सुनिश्चित करने का फैसला।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "अंतरराष्ट्रीय दूरसंचार संघ (ITU): दुनिया भर में 5G इंटरनेट उपयोगकर्ताओं की संख्या 2 अरब के पार", "summary": "हाई-स्पीड मोबाइल इंटरनेट से विकासशील देशों में शिक्षा और टेली-मेडिसिन का तेजी से प्रसार।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "संयुक्त राष्ट्र खाद्य एवं कृषि संगठन (FAO): वैश्विक खाद्य मूल्य सूचकांक में लगातार तीसरे महीने गिरावट", "summary": "अनाज और खाद्य तेलों की भरपूर फसल के चलते अंतरराष्ट्रीय बाजारों में आवश्यक वस्तुओं की कीमतें स्थिर।", "category_tag": "अंतरराष्ट्रीय"},
    {"title": "विश्व योग और समग्र स्वास्थ्य सम्मेलन: 120 देशों के प्रतिनिधियों ने पारंपरिक चिकित्सा पर मंथन किया", "summary": "मानसिक तनाव मुक्ति और दीर्घायु के लिए समग्र जीवनशैली को वैश्विक स्वास्थ्य प्रणाली में जोड़ने पर बल।", "category_tag": "अंतरराष्ट्रीय"},
]

def _clean_html_text(raw_text):
    if not raw_text:
        return ""
    text = html.unescape(str(raw_text))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _extract_rss_image(item):
    for elem in item.iter():
        tag_lower = elem.tag.lower()
        if tag_lower.endswith(("content", "thumbnail", "enclosure")):
            url = elem.attrib.get("url") or elem.attrib.get("href")
            if url and url.startswith("http") and not url.endswith(".mp3"):
                return url
    for child in item:
        raw = child.text or ""
        m = re.search(r'<img[^>]+src=[\'\"](https?://[^\'\"]+)[\'\"]', raw, re.IGNORECASE)
        if m:
            url = m.group(1)
            if "1x1" not in url and "pixel" not in url:
                return url
    return ""

def _is_duplicate_story(title, seen_titles, threshold=0.45):
    stopwords = {
        'के', 'की', 'का', 'में', 'पर', 'से', 'को', 'और', 'है', 'हैं', 'ने', 'भी', 'तो',
        'था', 'थी', 'थे', 'यह', 'वह', 'एक', 'इस', 'उस', 'news', 'live', 'update',
        'badi', 'khabar', 'breaking', 'बड़ी', 'खबर', 'लाइव'
    }
    toks1 = set(re.findall(r'[ऀ-ॿ\w]+', title.lower())) - stopwords
    if not toks1:
        return False
    for seen in seen_titles:
        toks2 = set(re.findall(r'[ऀ-ॿ\w]+', seen.lower())) - stopwords
        if not toks2:
            continue
        inter = toks1.intersection(toks2)
        union = toks1.union(toks2)
        if len(inter) / float(len(union)) > threshold:
            return True
    return False

def fetch_trending_news(category="NATION", max_items=100, edition=EDITION_MORNING):
    urls = NEWS_FEEDS.get(category, NEWS_FEEDS["NATION"])
    headlines = []
    seen_titles = []

    for url in urls:
        if len(headlines) >= max_items:
            break
        try:
            resp = requests.get(url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item"):
                    title = _clean_html_text(item.findtext("title", ""))
                    desc = _clean_html_text(item.findtext("description", ""))
                    source_el = item.find("source")
                    source = _clean_html_text(source_el.text) if source_el is not None and source_el.text else "News Desk"
                    media_url = _extract_rss_image(item)

                    clean_title = re.sub(r"\s+-\s+[^-]+$", "", title).strip() or title
                    if len(clean_title) < 10 or _is_duplicate_story(clean_title, seen_titles):
                        continue
                    seen_titles.append(clean_title)

                    headlines.append({
                        "title": clean_title,
                        "summary": desc[:280] if desc else clean_title,
                        "source": source,
                        "media_url": media_url,
                        "category_tag": "राष्ट्रीय" if len(headlines) % 2 == 0 else "अंतरराष्ट्रीय",
                    })
                    if len(headlines) >= max_items:
                        break
        except Exception:
            pass

    if len(headlines) < max_items:
        max_pool = max(len(NATIONAL_STORIES), len(INTERNATIONAL_STORIES))
        for p_i in range(max_pool):
            if p_i < len(NATIONAL_STORIES):
                n_item = NATIONAL_STORIES[p_i]
                if not _is_duplicate_story(n_item["title"], seen_titles):
                    seen_titles.append(n_item["title"])
                    headlines.append({
                        "title": n_item["title"],
                        "summary": n_item.get("summary", n_item["title"]),
                        "source": "विशेष संवाददाता",
                        "media_url": "",
                        "category_tag": n_item.get("category_tag", "राष्ट्रीय"),
                    })
            if len(headlines) >= max_items:
                break
            if p_i < len(INTERNATIONAL_STORIES):
                i_item = INTERNATIONAL_STORIES[p_i]
                if not _is_duplicate_story(i_item["title"], seen_titles):
                    seen_titles.append(i_item["title"])
                    headlines.append({
                        "title": i_item["title"],
                        "summary": i_item.get("summary", i_item["title"]),
                        "source": "वैश्विक डेस्क",
                        "media_url": "",
                        "category_tag": i_item.get("category_tag", "अंतरराष्ट्रीय"),
                    })
            if len(headlines) >= max_items:
                break

    return headlines[:max_items]

def _build_story_narration(idx, total, hl, language="hindi", edition=EDITION_MORNING, is_short=True):
    title = hl.get("title", "")
    summary = hl.get("summary", title)
    if summary.lower().startswith(title[:30].lower()):
        summary = title

    if language == "hindi":
        if is_short:
            # Viral Hook & Funnel Narration for YouTube Shorts
            if idx == 0:
                return f"रुकिए! पिछले 24 घंटे में देश और दुनिया में कई बड़े घटनाक्रम हुए हैं। पहली बड़ी ख़बर: {title}।"
            elif idx == total - 1:
                return f"और सबसे महत्वपूर्ण बात! देश और दुनिया की पूरी 100 बड़ी खबरों का महाबुलेटिन हमारे चैनल पर लाइव आ चुका है! पूरी 100 खबरें देखने के लिए नीचे रिलेटेड वीडियो लिंक पर क्लिक करें और चैनल को सब्सक्राइब करें।"
            elif idx == 1:
                return f"वहीं दूसरी बड़ी ख़बर: {title}। {summary[:60]}।"
            else:
                return f"तीसरा बड़ा अपडेट: {title}। {summary[:60]}।"
        else:
            if edition == EDITION_MORNING:
                # 100 Superfast News (~14 words per story = ~6.5 seconds)
                if idx == 0:
                    return f"नमस्कार! 24 घंटे की 100 बड़ी खबरों के महाबुलेटिन में आपका स्वागत है। अगर आप हमारे शॉर्ट्स देखकर आए हैं, तो पूरा 100 खबरों का सुपरफास्ट बुलेटिन शुरू होता है अब! खबर नंबर एक: {title}। {summary[:60]}।"
                elif idx == total - 1:
                    return f"और खबर नंबर सौ: {title}। ये थीं 24 घंटे की 100 बड़ी खबरें। अगर आपको यह सुपरफास्ट बुलेटिन पसंद आया तो वीडियो को लाइक करें और चैनल को सब्सक्राइब करें। नमस्कार।"
                else:
                    return f"खबर नंबर {idx + 1}: {title}। {summary[:60]}।"
            elif edition == EDITION_EVENING:
                if idx == 0:
                    return f"नमस्कार, शाम के महाबुलेटिन में आपका स्वागत है। दिनभर की टॉप 50 बड़ी खबरों की शुरुआत करते हैं खबर नंबर एक से: {title}। {summary}।"
                elif idx == total - 1:
                    return f"और खबर नंबर पचास: {title}। ये थीं आज शाम की 50 सबसे बड़ी खबरें। चैनल को अभी सब्सक्राइब करें, नमस्कार।"
                else:
                    return f"खबर नंबर {idx + 1}: {title}। {summary}।"
            else:
                if idx == 0:
                    return (
                        f"नमस्कार, चौबीस घंटे लाइव न्यूज़ के दोपहर महाबुलेटिन में आपका स्वागत है। "
                        f"आज हम दिनभर के तमाम बड़े राष्ट्रीय और अंतरराष्ट्रीय घटनाक्रमों का विस्तार से विश्लेषण करेंगे। "
                        f"शुरुआत करते हैं आज की सबसे अहम ख़बर के साथ: {title}। "
                        f"विस्तृत जानकारी के अनुसार, {summary}। "
                        f"इस पूरे मामले पर उच्च स्तर पर समीक्षा जारी है और आने वाले समय में इसके दूरगामी परिणाम देखने को मिलेंगे।"
                    )
                elif idx == total - 1:
                    return (
                        f"महाबुलेटिन के अंत में रुख करते हैं आज की एक और अहम ख़बर की ओर: {title}। "
                        f"ताज़ा अपडेट के मुताबिक, {summary}। "
                        f"हमारे संवाददाता ग्राउंड जीरो से हर पहलू पर नज़र बनाए हुए हैं। "
                        f"देश और दुनिया की हर बड़ी ख़बर के लिए चैनल को तुरंत सब्सक्राइब करें और अपनी राय कमेंट बॉक्स में लिखें। नमस्कार।"
                    )
                else:
                    transitions = [
                        "अब रुख करते हैं आज की अगली अहम ख़बर की ओर",
                        "वहीं दूसरी तरफ एक और महत्वपूर्ण घटनाक्रम सामने आ रहा है",
                        "दोपहर महाबुलेटिन में अब बात करते हैं इस बड़ी अपडेट की",
                        "इसके साथ ही अंतरराष्ट्रीय मंच से जुड़ी एक और बड़ी ख़बर पर नज़र डालते हैं",
                        "आगे बढ़ते हैं और देखते हैं यह विशेष रिपोर्ट",
                    ]
                    tr = transitions[idx % len(transitions)]
                    return f"{tr}: {title}। आधिकारिक सूत्रों और रिपोर्ट के अनुसार, {summary}।"
    else:
        if is_short:
            return f"Top breaking headline: {title}. Click the related video link below for the full 100-news broadcast."
        else:
            if idx == 0:
                return f"Welcome to our 24/7 Global News Broadcast. Story number one: {title}. {summary}."
            elif idx == total - 1:
                return f"And rounding out our bulletin tonight, story number {total}: {title}. Thank you for watching."
            else:
                return f"Story number {idx + 1}: {title}. {summary}."

def _build_local_fallback_script(category, headlines, is_short, is_breaking, anchor_gender, language, edition=EDITION_MORNING):
    cfg = EDITION_CONFIGS.get(edition, EDITION_CONFIGS[EDITION_MORNING])
    target_count = 4 if is_short else cfg["target_count"]

    if not headlines:
        headlines = fetch_trending_news(category=category, max_items=target_count, edition=edition)

    unique_headlines = []
    seen = []
    for h in headlines:
        t = h.get("title", "")
        if not _is_duplicate_story(t, seen):
            seen.append(t)
            unique_headlines.append(h)
        if len(unique_headlines) >= target_count:
            break

    top_title = unique_headlines[0]["title"] if unique_headlines else "देश और दुनिया की बड़ी ख़बरें"
    banner = cfg["badge_label"] if not is_short else "बड़ी ख़बर"

    scenes = []
    for idx, hl in enumerate(unique_headlines):
        sid = idx + 1
        kw = hl.get("title", top_title)
        nar = _build_story_narration(idx, len(unique_headlines), hl, language=language, edition=edition, is_short=is_short)
        counter_label = f"{cfg['counter_prefix']} {sid} / {len(unique_headlines)}" if not is_short else f"ख़बर {sid}"
        scenes.append({
            "scene_id": sid,
            "narration": nar,
            "subtitles": nar,
            "headline_banner": kw,
            "search_query": kw,
            "rss_image_url": hl.get("media_url", ""),
            "counter_text": counter_label,
            "category_tag": hl.get("category_tag", "राष्ट्रीय" if idx % 2 == 0 else "अंतरराष्ट्रीय"),
            "bulletin_label": cfg["bulletin_label"],
            "image_prompt": f"Wide-angle realistic television news photojournalism of {kw}, broadcast photography, 8k, no text",
            "camera_angle": "closeup" if idx % 2 == 1 else "wide",
        })

    ticker_items = [h["title"] for h in unique_headlines[:15]]
    if is_short:
        if scenes:
            scenes[-1]["counter_text"] = "👉 FULL BULLETIN"
            scenes[-1]["headline_banner"] = "पूरा 100 न्यूज़ महाबुलेटिन चैनल पर लाइव देखें"
            scenes[-1]["category_tag"] = "महाबुलेटिन"
        ticker_str = "  |  ".join(ticker_items) + "  |  👉 पूरा 100 न्यूज़ महाबुलेटिन देखने के लिए नीचे दिए गए Related Video लिंक पर क्लिक करें! चैनल को अभी Subscribe करें"
        video_title = f"🔴 5 बड़ी ख़बरें! पूरा 100 न्यूज़ बुलेटिन चैनल पर देखें #Shorts"
    else:
        ticker_str = "  |  ".join(ticker_items)
        video_title = f"{cfg['title_prefix']} | National & International 100 News"

    return {
        "category": category,
        "language": language,
        "anchor_gender": anchor_gender,
        "is_breaking": is_breaking,
        "is_short": is_short,
        "edition": edition,
        "title": video_title,
        "headline_banner": banner,
        "ticker_text": ticker_str,
        "scenes": scenes,
        "raw_headlines": unique_headlines,
    }

def generate_news_script(category=None, is_short=True, is_breaking=False, anchor_gender=None, edition=EDITION_MORNING):
    if not category or category == "AUTO":
        category = "NATION"
    cat_upper = category.upper()
    language = "english" if cat_upper == "WORLD" else "hindi"
    chosen_gender = _pick_anchor_gender(anchor_gender)
    cfg = EDITION_CONFIGS.get(edition, EDITION_CONFIGS[EDITION_MORNING])
    target_count = 4 if is_short else cfg["target_count"]
    headlines = fetch_trending_news(cat_upper, max_items=target_count, edition=edition)
    return _build_local_fallback_script(cat_upper, headlines, is_short=is_short, is_breaking=is_breaking, anchor_gender=chosen_gender, language=language, edition=edition)

# ================= 4. NEURAL VOICE ENGINE =================
async def _edge_tts_save(text, voice, rate, output_path):
    import edge_tts
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch="+0Hz")
    await asyncio.wait_for(comm.save(output_path), timeout=25.0)

def synthesize_broadcast_voice(text, output_path, category="NATION", gender="female", language="hindi"):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    clean_text = (text or "").strip() or "नमस्कार, ताज़ा खबरों के लिए हमारे साथ जुड़े रहिए।"
    cat_upper = (category or "NATION").upper()
    g_key = "male" if str(gender).lower() == "male" else "female"

    if str(language).lower() == "english" or cat_upper == "WORLD":
        voice = VOICE_MAP["WORLD"][g_key]
        rate = "+5%"
        lang_code = "en"
    else:
        voice = VOICE_MAP["NATION"][g_key]
        rate = "+8%"
        lang_code = "hi"

    for attempt in range(1, 3):
        try:
            asyncio.run(_edge_tts_save(clean_text, voice, rate, output_path))
            if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
                return output_path
        except Exception:
            pass

    try:
        from gtts import gTTS
        tts = gTTS(text=clean_text, lang=lang_code, slow=False)
        tts.save(output_path)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return output_path
    except Exception:
        pass

    est_sec = max(5.0, len(clean_text.split()) / 2.5)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000", "-t", f"{est_sec:.1f}", "-af", "volume=0.02", output_path],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
    )
    return output_path

# ================= 5. B-ROLL VISUAL ENGINE & INSTANT SWITCHER =================
def _validate_and_resize_image(raw_bytes, target_w, target_h):
    img = Image.open(BytesIO(raw_bytes)).convert("RGB")
    w, h = img.size
    if w < 250 or h < 200:
        raise ValueError("Image too small")
    arr = np.asarray(img, dtype=np.float32)
    if arr.std() < 12.0:
        raise ValueError("Blank image")

    target_ratio = target_w / float(target_h)
    src_ratio = w / float(h)
    if src_ratio > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))

    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    img = ImageEnhance.Contrast(img).enhance(1.06)
    img = ImageEnhance.Color(img).enhance(1.08)
    return img

def _fetch_pollinations_image(prompt, target_w, target_h):
    gen_w, gen_h = 768, 768
    clean_prompt = re.sub(r"[^\w\s,.-]", " ", prompt or "Editorial news photojournalism").strip()
    encoded = urllib.parse.quote(clean_prompt[:220])
    seed = random.randint(1000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={gen_w}&height={gen_h}&seed={seed}&model=turbo&nologo=true"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200 and len(resp.content) > 12000:
            return _validate_and_resize_image(resp.content, target_w, target_h)
    except Exception:
        pass
    return None

def create_broadcast_story_card(output_path, target_w=760, target_h=514, headline_text="", counter_text="ख़बर 1 / 100", category_tag="राष्ट्रीय", bulletin_label="100 SUPERFAST", base_img=None, scene_idx=0, is_short=False):
    if is_short and (category_tag == "महाबुलेटिन" or scene_idx == 3):
        # Dedicated Glowing Hook & CTA Card for YouTube Short Outro
        img = Image.new("RGB", (target_w, target_h), (12, 18, 48))
        draw_bg = ImageDraw.Draw(img)
        for y in range(target_h):
            r = int(14 + 30 * (y / target_h))
            g = int(18 + 10 * (y / target_h))
            b = int(48 + 40 * (y / target_h))
            draw_bg.line([(0, y), (target_w, y)], fill=(r, g, b))
        cx, cy = target_w // 2, int(target_h * 0.40)
        draw_bg.rounded_rectangle([40, cy - 145, target_w - 40, cy + 145], radius=20, fill=(185, 14, 28), outline=(255, 215, 0), width=5)
        draw_bg.polygon([(cx - 30, cy - 90), (cx + 40, cy - 55), (cx - 30, cy - 20)], fill=(255, 255, 255))
        draw_bilingual_text(draw_bg, (cx - 275, cy - 10), "🔴 पूरा 100 न्यूज़ महाबुलेटिन देखें", size=36, fill=(255, 255, 255))
        draw_bilingual_text(draw_bg, (cx - 330, cy + 45), "👉 नीचे RELATED VIDEO लिंक पर क्लिक करें!", size=30, fill=(255, 235, 75))
        draw_bg.rectangle([60, cy + 95, target_w - 60, cy + 100], fill=(255, 215, 0))
    elif base_img is not None:
        img = base_img.copy()
    else:
        img = Image.new("RGB", (target_w, target_h), (10, 18, 42))
        draw_bg = ImageDraw.Draw(img)
        for y in range(target_h):
            ratio = y / float(target_h)
            r = int(10 + 16 * ratio)
            g = int(20 + 36 * (1.0 - abs(ratio - 0.5) * 1.4))
            b = int(48 + 72 * (1.0 - ratio * 0.4))
            draw_bg.line([(0, y), (target_w, y)], fill=(r, g, b))
        cx, cy = int(target_w * 0.5), int(target_h * 0.40)
        for rad in (65, 130, 205, 290):
            draw_bg.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], outline=(38, 86, 155), width=1)
        draw_bg.line([(cx - 340, cy), (cx + 340, cy)], fill=(30, 68, 125), width=1)
        draw_bg.line([(cx, cy - 220), (cx, cy + 220)], fill=(30, 68, 125), width=1)

    draw = ImageDraw.Draw(img)

    # Top-Left Glowing Counter Badge
    badge_str = f"🔴 {bulletin_label}  |  {counter_text}"
    str_w = measure_bilingual_text(draw, badge_str, size=21 if not is_short else 26)
    badge_w = max(340 if not is_short else 420, str_w + 36)
    badge_h = 46 if not is_short else 58
    badge_y = 16 if not is_short else 24
    draw.rounded_rectangle([18, badge_y, 18 + badge_w, badge_y + badge_h], radius=8, fill=(195, 16, 32), outline=(255, 215, 0), width=2)
    draw.ellipse([28, badge_y + 14, 42, badge_y + 28], fill=(255, 255, 255))
    draw_bilingual_text(draw, (48, badge_y + 8), badge_str, size=21 if not is_short else 26, fill=(255, 255, 255))

    # Bottom Story Headline Box
    box_h = 136 if not is_short else 170
    box_y = target_h - box_h - (14 if not is_short else 20)
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle([16, box_y, target_w - 16, target_h - (14 if not is_short else 20)], radius=10, fill=(8, 14, 30, 240), outline=(250, 198, 0, 255), width=3)
    ov_draw.rectangle([18, box_y + 2, target_w - 18, box_y + 6], fill=(225, 20, 36, 255))

    cat_str = f" ● {category_tag} "
    cat_w = measure_bilingual_text(ov_draw, cat_str, size=18 if not is_short else 22) + 16
    ov_draw.rounded_rectangle([28, box_y + 12, 28 + cat_w, box_y + (38 if not is_short else 44)], radius=6, fill=(195, 18, 34, 255))
    draw_bilingual_text(ov_draw, (34, box_y + 13), cat_str, size=18 if not is_short else 22, fill=(255, 235, 80))

    clean_hl = (headline_text or "ताज़ा बड़ी ख़बर").strip()
    words = clean_hl.split()
    line1 = " ".join(words[:7 if not is_short else 6])
    line2 = " ".join(words[7 if not is_short else 6 : 14 if not is_short else 12])
    draw_bilingual_text(ov_draw, (28, box_y + (46 if not is_short else 54)), line1, size=25 if not is_short else 30, fill=(255, 255, 255))
    if line2:
        draw_bilingual_text(ov_draw, (28, box_y + (82 if not is_short else 98)), line2, size=25 if not is_short else 30, fill=(255, 235, 75))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img.save(output_path, "JPEG", quality=92)
    return output_path

def download_scene_image(prompt, output_path, is_short=True, search_query="", rss_image_url="", headline_text="", counter_text="", category_tag="राष्ट्रीय", bulletin_label="100 SUPERFAST", scene_idx=0):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    target_w = 1080 if is_short else 760
    target_h = 830 if is_short else 514

    base_img = None
    if rss_image_url and rss_image_url.startswith("http"):
        try:
            resp = requests.get(rss_image_url, headers=HEADERS, timeout=6)
            if resp.status_code == 200 and len(resp.content) > 12000:
                base_img = _validate_and_resize_image(resp.content, target_w, target_h)
        except Exception:
            pass

    if base_img is None:
        full_prompt = f"{prompt or headline_text}, television news photojournalism, natural lighting, 8k, no text"
        base_img = _fetch_pollinations_image(full_prompt, target_w, target_h)

    return create_broadcast_story_card(
        output_path=output_path,
        target_w=target_w,
        target_h=target_h,
        headline_text=headline_text,
        counter_text=counter_text or f"ख़बर {scene_idx + 1}",
        category_tag=category_tag or ("राष्ट्रीय" if scene_idx % 2 == 0 else "अंतरराष्ट्रीय"),
        bulletin_label=bulletin_label,
        base_img=base_img,
        scene_idx=scene_idx,
        is_short=is_short,
    )

# ================= 6. PHOTOREALISTIC REAL ANCHOR RIG =================
class RealStudioAnchor:
    is_real = True

    def __init__(self, video_path, target_w=1080, target_h=986):
        self.w = target_w
        self.h = target_h
        self.frames = []
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
                video_path
            ]
            dim_str = subprocess.check_output(probe_cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
            fw, fh = [int(x) for x in dim_str.split("x")]
            target_ratio = float(target_w) / float(target_h)
            crop_w = int(fh * target_ratio)

            if 800 <= fw <= 900 and 450 <= fh <= 500:
                x1 = 50
                vf = f"crop={crop_w}:{fh}:{x1}:0,scale={target_w}:{target_h}"
            else:
                vf = f"crop=ih*{target_w}/{target_h}:ih:(iw-ih*{target_w}/{target_h})/2:0,scale={target_w}:{target_h}"

            cmd = ["ffmpeg", "-y", "-v", "error", "-i", video_path, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            frame_sz = target_w * target_h * 3
            while True:
                raw = proc.stdout.read(frame_sz)
                if len(raw) < frame_sz:
                    break
                self.frames.append(np.frombuffer(raw, dtype=np.uint8).reshape((target_h, target_w, 3)))
            proc.wait()
        except Exception as e:
            logger.warning(f"FFmpeg anchor frame loader error: {e}")

        self.total = len(self.frames)
        logger.info(f"Loaded {self.total} photorealistic anchor frames ({target_w}x{target_h}) from {video_path} [Zero-Watermark Filter Active]")
        if self.total > 15:
            self.speak_start = min(18, self.total // 4)
            self.speak_end = min(92, int(self.total * 0.78))
            self.pause_frames = list(range(0, self.speak_start)) + list(range(self.speak_end, self.total))
        else:
            self.speak_start = 0
            self.speak_end = max(1, self.total)
            self.pause_frames = list(range(self.total)) or [0]

    def render_frame(self, t, speech_amp=0.5, word_idx=0):
        if not self.frames:
            return np.zeros((self.h, self.w, 3), dtype=np.uint8)
        if speech_amp > 0.10:
            speak_len = max(1, self.speak_end - self.speak_start)
            phase = (t * 22.0 + word_idx * 1.5) % (speak_len * 2)
            idx = (self.speak_end - 1 - int(phase - speak_len)) if phase >= speak_len else (self.speak_start + int(phase))
            return self.frames[max(0, min(self.total - 1, idx))]
        else:
            pause_len = max(1, len(self.pause_frames))
            p_idx = int(t * 12.0) % pause_len
            return self.frames[self.pause_frames[p_idx]]

def find_real_anchor_video(preferred_gender="female"):
    g = str(preferred_gender or "female").lower()
    if g == "male":
        priority = [
            "anchor_real_male.mp4",
            "assets/anchor_real_male.mp4",
            "1000122786.mp4",
            "assets/1000122786.mp4",
            "user_uploaded_files/ttl=63d/user_uploaded/1000122786.mp4",
            "anchor_real.mp4",
            "assets/anchor_real.mp4",
            "anchor_real_female.mp4",
            "assets/anchor_real_female.mp4",
            "anchor_studio.mp4",
            "assets/anchor_studio.mp4",
        ]
    else:
        priority = [
            "anchor_real_female.mp4",
            "assets/anchor_real_female.mp4",
            "anchor_real.mp4",
            "assets/anchor_real.mp4",
            "PixVerse_V6_Image_Text_540P_Make_a_female_anco.mp4",
            "assets/PixVerse_V6_Image_Text_540P_Make_a_female_anco.mp4",
            "user_uploaded_files/ttl=63d/user_uploaded/PixVerse_V6_Image_Text_540P_Make_a_female_anco.mp4",
            "1000121747.mp4",
            "assets/1000121747.mp4",
            "user_uploaded_files/ttl=63d/user_uploaded/1000121747.mp4",
            "anchor_studio.mp4",
            "assets/anchor_studio.mp4",
            "anchor_real_male.mp4",
            "assets/anchor_real_male.mp4",
            "1000122786.mp4",
            "assets/1000122786.mp4",
        ]

    for c in priority:
        if os.path.exists(c) and os.path.getsize(c) > 20000:
            return c

    for p in glob.glob("user_uploaded_files/*/*/*.mp4") + glob.glob("assets/*.mp4") + glob.glob("*.mp4"):
        base = os.path.basename(p).lower()
        if not base.startswith(("short_", "long_", "final_")) and "output" not in p and os.path.getsize(p) > 20000:
            return p
    return None

class StudioAnimeAnchor:
    def __init__(self, gender="female", width=1080, height=986, desk_ratio=0.56):
        self.gender = "male" if str(gender).lower() == "male" else "female"
        self.w = width
        self.h = height
        self.desk_y = int(height * desk_ratio)

    def render_frame(self, t, speech_amp, word_idx=0):
        img = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        img[:, :] = (15, 24, 52)
        return img

# ================= 7. SUBTITLE CARDS & TIMINGS =================
def _build_word_synced_subtitle_cards(W, sub_h, word_timings, language="hindi", is_short=True):
    dummy_img = Image.new("RGB", (W, sub_h))
    dummy_draw = ImageDraw.Draw(dummy_img)
    sub_font_sz = 30 if is_short else 22
    speaker_tag = "एंकर:" if language == "hindi" else "ANCHOR:"
    tag_px = measure_bilingual_text(dummy_draw, speaker_tag, size=sub_font_sz) + 18
    start_x = 58 + tag_px
    max_line_w = W - start_x - 36
    space_px = max(8, int(sub_font_sz * 0.32))
    ty = (sub_h - sub_font_sz) // 2 - 2

    for wt in word_timings:
        wt["sub_px"] = measure_bilingual_text(dummy_draw, wt["word"], size=sub_font_sz)

    lines, cur_line, cur_w = [], [], 0
    for wt in word_timings:
        w_px = wt["sub_px"]
        if cur_line and (cur_w + space_px + w_px > max_line_w):
            lines.append(cur_line)
            cur_line = [wt]
            cur_w = w_px
        else:
            cur_line.append(wt)
            cur_w += (space_px + w_px) if len(cur_line) > 1 else w_px
    if cur_line:
        lines.append(cur_line)
    if not lines:
        lines = [[{"word": "", "start": 0.0, "end": 1.0, "idx": 0, "sub_px": 10}]]

    total_words = max(1, len(word_timings))
    sub_cards = [None] * total_words

    for ln in lines:
        base_up = Image.new("RGB", (W, sub_h), (10, 14, 28))
        du = ImageDraw.Draw(base_up)
        du.rectangle([0, 0, W, 3], fill=(0, 195, 255))
        du.rounded_rectangle([16, 6, W - 16, sub_h - 6], radius=10, fill=(18, 24, 46), outline=(255, 205, 0), width=2)
        cy_dot = sub_h // 2
        du.ellipse([32, cy_dot - 7, 46, cy_dot + 7], fill=(235, 30, 45))
        draw_bilingual_text(du, (56, ty), speaker_tag, size=sub_font_sz, fill=(255, 205, 0))

        base_sp = base_up.copy()
        ds = ImageDraw.Draw(base_sp)

        tx = start_x
        line_words = []
        for wt in ln:
            w_str = wt["word"]
            w_px = wt["sub_px"]
            draw_bilingual_text(du, (tx, ty), w_str, size=sub_font_sz, fill=(160, 188, 225))
            draw_bilingual_text(ds, (tx, ty), w_str, size=sub_font_sz, fill=(255, 255, 255))
            line_words.append((wt["idx"], w_str, tx, w_px))
            tx += w_px + space_px

        running_img = base_up.copy()
        for (w_idx, w_str, tx, w_px) in line_words:
            sc_img = running_img.copy()
            sc_draw = ImageDraw.Draw(sc_img)
            sc_draw.rounded_rectangle([tx - 4, ty - 2, tx + w_px + 4, ty + sub_font_sz + 5], radius=6, fill=(205, 18, 34), outline=(255, 215, 0), width=2)
            draw_bilingual_text(sc_draw, (tx, ty), w_str, size=sub_font_sz, fill=(255, 238, 75))
            sub_cards[w_idx] = np.asarray(sc_img, dtype=np.uint8)
            box = (max(0, tx - 2), max(0, ty - 2), min(W, tx + w_px + 4), min(sub_h, ty + sub_font_sz + 6))
            running_img.paste(base_sp.crop(box), box)

    return sub_cards

# ================= 8. FULL-FRAME BROADCAST VIDEO RENDERER =================
def _get_audio_duration(audio_path):
    try:
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=10).decode().strip()
        return max(2.0, float(out))
    except Exception:
        return 6.5

def _extract_audio_envelope(audio_path, duration, fps=20):
    n_frames = max(1, int(math.ceil(duration * fps)) + 2)
    sample_rate = 1200
    try:
        cmd = ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "-"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20)
        pcm = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32)
        if pcm.size < 10:
            raise ValueError("Empty PCM")
        samples_per_frame = max(1, sample_rate // fps)
        target_len = n_frames * samples_per_frame
        pcm = np.pad(pcm, (0, max(0, target_len - pcm.size)))[:target_len]
        frames_pcm = pcm.reshape((n_frames, samples_per_frame))
        rms = np.sqrt(np.mean(frames_pcm ** 2, axis=1))
        p95 = np.percentile(rms, 95) if rms.size > 0 else 1.0
        env = np.clip(rms / max(p95, 100.0), 0.0, 1.0)
        return np.convolve(env, np.array([0.2, 0.6, 0.2], dtype=np.float32), mode="same")
    except Exception:
        t = np.linspace(0, duration, n_frames)
        return 0.45 + 0.45 * np.abs(np.sin(2.0 * np.pi * 3.8 * t))

def _create_bgm_wav(total_duration, bgm_path="temp/broadcast_bgm.wav"):
    import wave
    sr = 16000
    loop_sec = min(20.0, total_duration)
    n_loop = int(loop_sec * sr)
    t = np.linspace(0, loop_sec, n_loop, endpoint=False)
    pad = 0.35 * np.sin(2 * np.pi * 110.0 * t) + 0.25 * np.sin(2 * np.pi * 165.0 * t)
    pulse = (0.5 + 0.5 * np.sin(2 * np.pi * 3.5 * t)) ** 3
    beeps = 0.20 * np.sin(2 * np.pi * 440.0 * t) * pulse
    wave_loop = np.clip((pad + beeps) * 0.04, -0.9, 0.9)
    pcm_loop = (wave_loop * 32767).astype(np.int16)
    repeats = int(math.ceil(total_duration / max(1.0, loop_sec)))
    full_pcm = np.tile(pcm_loop, repeats)[: int(total_duration * sr)]

    os.makedirs(os.path.dirname(os.path.abspath(bgm_path)), exist_ok=True)
    with wave.open(bgm_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(full_pcm.tobytes())
    return bgm_path if os.path.exists(bgm_path) else None

def build_news_video(script_data, scene_assets, output_path, is_short=True):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    fps = 24 if is_short else 20
    W, H = (1080, 1920) if is_short else (1280, 720)

    language = script_data.get("language", "hindi")
    category = script_data.get("category", "NATION").upper()
    anchor_gender = script_data.get("anchor_gender", "female")
    edition = script_data.get("edition", EDITION_MORNING)
    cfg = EDITION_CONFIGS.get(edition, EDITION_CONFIGS[EDITION_MORNING])
    ticker_raw = script_data.get("ticker_text") or script_data.get("headline_banner") or "LIVE BREAKING NEWS UPDATES"

    ticker_clean = re.sub(r"•", " | ", ticker_raw)
    ticker_unit = f"   [LIVE 24x7]  {ticker_clean}   |   BREAKING NEWS   |   "
    ticker_full = ticker_unit * 4

    ticker_h = 58 if is_short else 44
    ticker_font_sz = 30 if is_short else 23
    ticker_w = max(W * 4, len(ticker_full) * 18)
    ticker_strip = Image.new("RGB", (ticker_w, ticker_h), (248, 198, 0))
    t_draw = ImageDraw.Draw(ticker_strip)
    t_draw.rectangle([0, 0, ticker_w, 4], fill=(190, 15, 25))
    end_x = draw_bilingual_text(t_draw, (20, (ticker_h - ticker_font_sz) // 2 - 2), ticker_full, size=ticker_font_sz, fill=(10, 12, 18))
    unit_px = max(450, (end_x - 20) // 4)
    ticker_arr = np.asarray(ticker_strip, dtype=np.uint8)

    if is_short:
        broll_win_w, broll_win_h = W, 830
        strap_h = 104
        anchor_w = W
        anchor_h = H - broll_win_h - strap_h  # exactly 986px (830 + 104 + 986 = 1920)
        sub_h = 96
        desk_ratio = 0.56
    else:
        header_h = 46
        strap_h = 58
        sub_h = 58
        body_h = H - header_h - strap_h - sub_h - ticker_h  # 514px
        anchor_w, anchor_h = 520, body_h  # 520x514
        broll_win_w, broll_win_h = W - anchor_w, body_h  # 760x514
        desk_ratio = 0.86

    real_video = find_real_anchor_video(anchor_gender)
    if real_video:
        logger.info(f"🎥 Using Photorealistic Real TV News Anchor from {real_video}...")
        animator = RealStudioAnchor(video_path=real_video, target_w=anchor_w, target_h=anchor_h)
    else:
        logger.info("🎨 Using Studio News Anchor...")
        animator = StudioAnimeAnchor(gender=anchor_gender, width=anchor_w, height=anchor_h, desk_ratio=desk_ratio)

    if is_short:
        badge_on = Image.new("RGB", (440, 56), (14, 22, 48))
        bo_draw = ImageDraw.Draw(badge_on)
        bo_draw.rectangle([0, 0, 215, 56], fill=(230, 18, 32))
        bo_draw.ellipse([18, 18, 38, 38], fill=(255, 255, 255))
        draw_bilingual_text(bo_draw, (48, 11), "LIVE 24x7", size=26, fill=(255, 255, 255))
        bo_draw.rectangle([215, 0, 440, 56], fill=(14, 22, 48), outline=(255, 200, 0), width=2)
        draw_bilingual_text(bo_draw, (235, 11), category, size=26, fill=(255, 215, 0))
        badge_on_arr = np.asarray(badge_on, dtype=np.uint8)
    else:
        hdr_img = Image.new("RGB", (W, header_h), (12, 18, 38))
        h_draw = ImageDraw.Draw(hdr_img)
        h_draw.rectangle([0, header_h - 3, W, header_h], fill=(250, 195, 0))
        h_draw.rounded_rectangle([16, 6, 178, header_h - 8], radius=6, fill=(220, 18, 32))
        h_draw.ellipse([28, 16, 40, 28], fill=(255, 255, 255))
        draw_bilingual_text(h_draw, (48, 9), "LIVE 24x7", size=20, fill=(255, 255, 255))
        h_draw.rounded_rectangle([190, 6, 350, header_h - 8], radius=6, fill=(22, 34, 68), outline=(250, 195, 0), width=2)
        draw_bilingual_text(h_draw, (208, 9), category, size=20, fill=(255, 215, 0))
        hdr_title = cfg.get("header_title", "24x7 LIVE SPECIAL REPORT")
        draw_bilingual_text(h_draw, (375, 9), hdr_title, size=21, fill=(240, 245, 255))
        header_arr = np.asarray(hdr_img, dtype=np.uint8)

    prepared_scenes = []
    concat_list_path = "temp/audio_concat.txt"
    total_duration = 0.0

    with open(concat_list_path, "w", encoding="utf-8") as f_concat:
        for idx, asset in enumerate(scene_assets):
            dur = _get_audio_duration(asset["audio_path"])
            env = _extract_audio_envelope(asset["audio_path"], dur, fps=fps)
            f_concat.write(f"file '{os.path.abspath(asset['audio_path'])}'\n")

            img_p = asset["image_path"]
            broll_pil = Image.open(img_p).convert("RGB").resize(
                (int(broll_win_w * 1.05), int(broll_win_h * 1.05)), Image.Resampling.BILINEAR
            )
            broll_base_arr = np.asarray(broll_pil, dtype=np.uint8)

            headline_banner = (asset.get("headline_banner") or script_data.get("headline_banner") or "BREAKING NEWS").strip()
            narration = (asset.get("subtitles") or asset.get("narration") or headline_banner).strip()

            word_timings = build_word_timings(narration, dur)
            sub_cards = _build_word_synced_subtitle_cards(W=W, sub_h=sub_h, word_timings=word_timings, language=language, is_short=is_short)

            badge_label = cfg.get("badge_label", "बड़ी ख़बर") if not is_short else "बड़ी ख़बर"
            tag_w = 225 if is_short else 185
            strap_font_sz = 28 if is_short else 22
            hl_font_sz = 32 if is_short else 24

            strap_left_img = Image.new("RGB", (tag_w, strap_h), (155, 12, 24))
            sl_draw = ImageDraw.Draw(strap_left_img)
            sl_draw.rectangle([0, 0, tag_w, 5], fill=(255, 205, 0))
            sl_draw.rectangle([0, strap_h - 5, tag_w, strap_h], fill=(255, 205, 0))
            sl_draw.polygon([(0, 5), (tag_w, 5), (tag_w - 22, strap_h - 5), (0, strap_h - 5)], fill=(250, 195, 0))
            draw_bilingual_text(sl_draw, (18, (strap_h - strap_font_sz) // 2 - 2), badge_label, size=strap_font_sz, fill=(15, 15, 20))
            strap_left_arr = np.asarray(strap_left_img, dtype=np.uint8)

            hl_loop_str = f"   {headline_banner}   •   {narration[:100]}   •   " * 3
            right_w = W - tag_w
            hl_strip_w = max(right_w * 3, len(hl_loop_str) * 18)
            hl_strip_img = Image.new("RGB", (hl_strip_w, strap_h), (155, 12, 24))
            hr_draw = ImageDraw.Draw(hl_strip_img)
            hr_draw.rectangle([0, 0, hl_strip_w, 5], fill=(255, 205, 0))
            hr_draw.rectangle([0, strap_h - 5, hl_strip_w, strap_h], fill=(255, 205, 0))
            hl_end_x = draw_bilingual_text(hr_draw, (16, (strap_h - hl_font_sz) // 2 - 2), hl_loop_str, size=hl_font_sz, fill=(255, 255, 255))
            hl_unit_px = max(300, (hl_end_x - 16) // 3)
            strap_right_arr = np.asarray(hl_strip_img, dtype=np.uint8)

            prepared_scenes.append({
                "idx": idx, "dur": dur, "start_t": total_duration, "env": env,
                "broll_base_arr": broll_base_arr, "word_timings": word_timings,
                "sub_cards": sub_cards, "strap_left_arr": strap_left_arr,
                "strap_right_arr": strap_right_arr, "hl_unit_px": hl_unit_px, "tag_w": tag_w,
            })
            total_duration += dur

    merged_voice_wav = "temp/merged_voice.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_list_path, "-ar", "24000", "-ac", "1", merged_voice_wav],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
    )
    bgm_wav = _create_bgm_wav(total_duration + 3.0, "temp/broadcast_bgm.wav")
    final_audio_wav = "temp/final_mixed_audio.wav"
    if bgm_wav and os.path.exists(merged_voice_wav):
        subprocess.run(
            ["ffmpeg", "-y", "-i", merged_voice_wav, "-i", bgm_wav, "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2[aout]", "-map", "[aout]", final_audio_wav],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120,
        )
    else:
        final_audio_wav = merged_voice_wav

    logger.info(f"🎬 Rendering {fps}fps {'SHORT (1080x1920)' if is_short else f'LONG ({edition} - {len(prepared_scenes)} Stories)'} Video ({total_duration:.1f}s = {total_duration/60.0:.1f} min)...")
    ffmpeg_cmd = [
        "ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{W}x{H}", "-pix_fmt", "rgb24", "-r", str(fps),
        "-i", "-", "-i", final_audio_wav,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k", "-shortest", output_path,
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    mv = memoryview(canvas)

    for sc in prepared_scenes:
        n_frames = max(1, int(round(sc["dur"] * fps)))
        idx, dur, env = sc["idx"], sc["dur"], sc["env"]
        broll_base_arr = sc["broll_base_arr"]
        word_timings = sc["word_timings"]
        sub_cards = sc["sub_cards"]
        strap_left_arr = sc["strap_left_arr"]
        strap_right_arr = sc["strap_right_arr"]
        hl_unit_px = sc["hl_unit_px"]
        tag_w = sc["tag_w"]
        right_w = W - tag_w
        scene_start_t = sc["start_t"]
        bh, bw, _ = broll_base_arr.shape
        max_dx = max(1, bw - broll_win_w)
        max_dy = max(1, bh - broll_win_h)

        cur_w_idx = 0
        n_words = len(word_timings)

        for f_i in range(n_frames):
            t = f_i / float(fps)
            gt = scene_start_t + t
            speech_amp = float(env[min(len(env) - 1, f_i)])

            while (cur_w_idx + 1 < n_words) and (t >= word_timings[cur_w_idx]["end"]):
                cur_w_idx += 1

            prog = min(1.0, max(0.0, t / max(0.1, dur)))
            crop_x = int(max_dx * (0.5 + 0.3 * math.sin(prog * math.pi)))
            crop_y = int(max_dy * (0.5 + 0.3 * math.cos(prog * math.pi)))

            broll_view = broll_base_arr[crop_y : crop_y + broll_win_h, crop_x : crop_x + broll_win_w]
            anchor_arr = animator.render_frame(gt, speech_amp=speech_amp, word_idx=cur_w_idx)

            scroll_x = int(gt * 150) % max(1, min(unit_px, ticker_arr.shape[1] - W - 1))
            hl_scroll_x = int(t * 95) % max(1, min(hl_unit_px, strap_right_arr.shape[1] - right_w - 1))

            if is_short:
                canvas[0:830, :, :] = broll_view
                canvas[28:84, 28:468, :] = badge_on_arr
                canvas[830:934, 0:tag_w, :] = strap_left_arr
                canvas[830:934, tag_w:W, :] = strap_right_arr[:, hl_scroll_x : hl_scroll_x + right_w, :]
                canvas[934:1920, :, :] = anchor_arr

                bar_w = int(W * (0.18 + 0.72 * speech_amp))
                x_s = (W - bar_w) // 2
                canvas[1756:1764, x_s : x_s + bar_w, :] = (255, 65, 75)
                canvas[1764:1860, :, :] = sub_cards[cur_w_idx]
                canvas[1860:1918, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]
            else:
                canvas[0:46, :, :] = header_arr
                canvas[46:560, 0:520, :] = anchor_arr
                canvas[46:560, 516:524, :] = (250, 195, 0)
                canvas[46:560, 520:1280, :] = broll_view
                canvas[560:618, 0:tag_w, :] = strap_left_arr
                canvas[560:618, tag_w:W, :] = strap_right_arr[:, hl_scroll_x : hl_scroll_x + right_w, :]
                canvas[618:676, :, :] = sub_cards[cur_w_idx]
                canvas[676:720, :, :] = ticker_arr[:, scroll_x : scroll_x + W, :]

            try:
                proc.stdin.write(mv)
            except (BrokenPipeError, IOError):
                break

    try:
        proc.stdin.close()
    except Exception:
        pass
    proc.wait(timeout=1200)
    logger.info(f"✅ Broadcast Video Rendered: {output_path} ({os.path.getsize(output_path) // 1024} KB)")
    return output_path

def cleanup_temp_files():
    os.makedirs("temp", exist_ok=True)
    for f in glob.glob("temp/*"):
        try:
            os.remove(f)
        except Exception:
            pass

def _mirror_video_for_github_artifacts(video_path, is_short=True):
    if not os.path.exists(video_path):
        return
    base_name = os.path.basename(video_path)
    targets = [
        "final_short.mp4" if is_short else "final_long.mp4",
        os.path.join("AI_NEWS_CHANNEL_OUTPUT", "shorts" if is_short else "long_videos", base_name),
    ]
    for dst in targets:
        try:
            d_dir = os.path.dirname(dst)
            if d_dir:
                os.makedirs(d_dir, exist_ok=True)
            shutil.copy2(video_path, dst)
            logger.info(f"📦 Saved artifact copy for download: {dst}")
        except Exception as e:
            logger.warning(f"Artifact mirror warning ({dst}): {e}")

def _sanitize_youtube_title(raw_title, is_short=True):
    clean = re.sub(r"[<>\"']", "", str(raw_title or "LIVE Breaking News Update"))
    clean = re.sub(r"\s+", " ", clean).strip()
    if is_short:
        clean = re.sub(r"#shorts", "", clean, flags=re.IGNORECASE).strip()
        return f"{clean[:68]} #Shorts".strip()
    else:
        clean = re.sub(r"#shorts", "", clean, flags=re.IGNORECASE).strip()
        return clean[:80] or "🔴 LIVE महाबुलेटिन: आज की सबसे बड़ी ख़बरें"

def _append_upload_report(text):
    try:
        os.makedirs("output", exist_ok=True)
        report_path = os.path.join("output", "YOUTUBE_UPLOAD_REPORT.txt")
        with open(report_path, "a", encoding="utf-8") as rf:
            rf.write(text.rstrip() + "\n")
    except Exception:
        pass
    step_sum = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_sum:
        try:
            with open(step_sum, "a", encoding="utf-8") as sf:
                sf.write(text.rstrip() + "\n\n")
        except Exception:
            pass

def _get_youtube_access_token():
    cid = (YT_CLIENT_ID or "").strip()
    csec = (YT_CLIENT_SECRET or "").strip()
    rtok = (YT_REFRESH_TOKEN or "").strip()

    if not (cid and csec and rtok):
        missing = []
        if not cid: missing.append("YT_CLIENT_ID")
        if not csec: missing.append("YT_CLIENT_SECRET")
        if not rtok: missing.append("YT_REFRESH_TOKEN")
        return None, f"Missing GitHub Secrets: {', '.join(missing)}"

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={"client_id": cid, "client_secret": csec, "refresh_token": rtok, "grant_type": "refresh_token"},
            timeout=20,
        )
        if resp.status_code == 200:
            token = resp.json().get("access_token")
            if token:
                return token, None
        return None, f"OAuth2 Error: {resp.text[:300]}"
    except Exception as e:
        return None, f"Network error: {e}"

def verify_youtube_credentials():
    logger.info("🔍 PRE-FLIGHT YOUTUBE OAUTH2 DIAGNOSTIC")
    token, err = _get_youtube_access_token()
    if not token:
        logger.error(f"❌ YOUTUBE AUTH FAILED: {err}")
        _append_upload_report(f"### ❌ YouTube OAuth Failed: `{err}`")
        return False
    logger.info("✅ YouTube OAuth2 Access Token Valid & Active!")
    _append_upload_report("### ✅ YouTube OAuth2 Token Active")
    return True

def build_comprehensive_youtube_metadata(script_data, is_short=False):
    scenes = script_data.get("scenes", [])
    title = script_data.get("title", "🔴 LIVE महाबुलेटिन: 24 घंटे की 100 बड़ी ख़बरें")

    if is_short:
        clean_desc = "\n\n".join([
            f"{title}",
            "⚡ 24 घंटे की 5 सबसे बड़ी और अहम सुर्खियां!",
            "👉 देश और दुनिया की पूरी 100 बड़ी खबरों का सुपरफास्ट लाइव महाबुलेटिन देखने के लिए नीचे दिए गए 'Related Video' लिंक पर क्लिक करें या सीधे हमारे चैनल पर जाएं!",
            "📺 पूरा 100 न्यूज़ महाबुलेटिन:\n\"🔴 LIVE महाबुलेटिन: 24 घंटे की 100 बड़ी ख़बरें | TOP 100 SUPERFAST NEWS\"",
            "📌 चैनल को अभी Subscribe करें ताकि हर बड़ी खबर सबसे पहले मिले!",
            "#Shorts #HindiNews #Top100News #BreakingNews #SuperfastNews #LiveNews #NewsToday #HindiSamachar"
        ])
        tags = [
            "Hindi News Shorts", "Top 100 News", "Breaking News Hindi",
            "Superfast News", "Live News Hindi", "Today Headlines",
            "National News", "International News", "Shorts",
            "Viral Shorts", "100 Khabrein", "News Bulletin"
        ]
        return clean_desc, tags

    desc_lines = []
    desc_lines.append(f"{title}\n")
    desc_lines.append(
        f"आज के इस विशेष महाबुलेटिन में देखिए देश और दुनिया की {len(scenes)} सबसे बड़ी व महत्वपूर्ण खबरें सुपरफास्ट अंदाज में। "
        f"राष्ट्रीय, अंतरराष्ट्रीय, अंतरिक्ष (ISRO), रक्षा, अर्थव्यवस्था, तकनीक और खेल जगत के हर बड़े घटनाक्रम की पूरी कवरेज।\n"
    )
    desc_lines.append(f"📌 बुलेटिन में शामिल प्रमुख खबरें व टाइमलाइन ({len(scenes)} Stories Chapters):")
    for idx, sc in enumerate(scenes):
        hl = sc.get("headline_banner", "")
        cat = sc.get("category_tag", "प्रमुख")
        desc_lines.append(f"{idx + 1}. [{cat}] {hl}")

    desc_lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    desc_lines.append("🔹 कवरेज के मुख्य विषय (Key Coverage Categories):")
    desc_lines.append("• 🇮🇳 राष्ट्रीय व प्रादेशिक समाचार (National & State News)")
    desc_lines.append("• 🌍 अंतरराष्ट्रीय भू-राजनीति व कूटनीति (International & Global Affairs)")
    desc_lines.append("• 🚀 अंतरिक्ष, इसरो व विज्ञान (ISRO, Space & Science)")
    desc_lines.append("• 🛡️ रक्षा व सैन्य आधुनिकीकरण (Defence & Security)")
    desc_lines.append("• 📈 अर्थव्यवस्था, शेयर बाजार व व्यापार (Economy, Markets & Business)")
    desc_lines.append("• ⚡ तकनीक, आर्टिफिशियल इंटेलिजेंस व नवाचार (Technology & AI)")
    desc_lines.append("• 🏏 खेल, क्रिकेट व एथलेटिक्स (Sports & Youth)")
    desc_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    desc_lines.append("🔔 निष्पक्ष, सटीक और सबसे तेज़ खबरों के लिए हमारे चैनल को सब्सक्राइब करें और बेल आइकन दबाएं।\n")
    desc_lines.append("#Top100News #HindiNews #NationalNews #InternationalNews #SuperfastNews #LiveNews #BreakingNews #ISRO #IndianEconomy #DefenceNews #WorldNewsHindi")

    full_description = "\n".join(desc_lines)[:4500]

    base_tags = [
        "Top 100 News", "100 Khabrein", "Superfast News", "Hindi News Live",
        "National News Hindi", "International News Hindi", "Today Breaking News",
        "Aaj Ki Badi Khabrein", "Desh Duniya Ki Khabar", "ISRO Space News",
        "Defence News India", "Economy News Hindi", "World News in Hindi",
        "Nonstop 100", "Hindi Samachar", "Live Bulletin"
    ]
    topic_keywords = []
    stopwords = {"में", "पर", "के", "की", "का", "से", "को", "और", "है", "हैं", "ने", "भी", "नए", "नई", "हुआ", "हुई", "किए", "शुरू", "बड़ा", "बड़ी"}
    for sc in scenes:
        words = re.findall(r'[ऀ-ॿ\w]+', sc.get("headline_banner", ""))
        for w in words:
            if len(w) > 3 and w not in stopwords and w not in topic_keywords:
                topic_keywords.append(w)
            if len(topic_keywords) >= 35:
                break
        if len(topic_keywords) >= 35:
            break

    all_candidate_tags = base_tags + topic_keywords
    final_tags = []
    total_len = 0
    for tag in all_candidate_tags:
        ctag = re.sub(r'[<>,"\']', '', tag).strip()
        if ctag and ctag not in final_tags:
            tag_len = len(ctag) + 1
            if total_len + tag_len < 480:
                final_tags.append(ctag)
                total_len += tag_len
            else:
                break

    return full_description, final_tags

def upload_to_youtube(video_path, script_data, is_short=True):
    label = "SHORT (9:16)" if is_short else "LONG VIDEO (16:9)"
    if not os.path.exists(video_path):
        return None
    file_size = os.path.getsize(video_path)
    access_token, auth_err = _get_youtube_access_token()
    if not access_token:
        _append_upload_report(f"- ❌ **{label} Upload Skipped**: `{auth_err}`")
        return None

    title = _sanitize_youtube_title(script_data.get("title", ""), is_short=is_short)
    description, tags = build_comprehensive_youtube_metadata(script_data, is_short=is_short)

    body = {
        "snippet": {
            "title": title, "description": description, "tags": tags,
            "categoryId": "25", "defaultLanguage": "hi", "defaultAudioLanguage": "hi",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }

    for attempt in range(1, 4):
        try:
            logger.info(f"🚀 Uploading {label}: '{title}' [Tags: {len(tags)}, Desc: {len(description)} chars]")
            init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
            init_headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Length": str(file_size),
                "X-Upload-Content-Type": "video/mp4",
            }
            init_resp = requests.post(init_url, headers=init_headers, json=body, timeout=30)
            if init_resp.status_code not in (200, 201):
                time.sleep(3)
                continue

            upload_url = init_resp.headers.get("Location")
            if not upload_url:
                continue

            chunk_size = 8 * 1024 * 1024
            uploaded_bytes = 0
            vid_id = None

            with open(video_path, "rb") as vf:
                while uploaded_bytes < file_size:
                    chunk = vf.read(chunk_size)
                    if not chunk:
                        break
                    start_b = uploaded_bytes
                    end_b = uploaded_bytes + len(chunk) - 1
                    put_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Length": str(len(chunk)),
                        "Content-Type": "video/mp4",
                        "Content-Range": f"bytes {start_b}-{end_b}/{file_size}",
                    }
                    put_resp = requests.put(upload_url, headers=put_headers, data=chunk, timeout=180)
                    if put_resp.status_code in (200, 201):
                        vid_id = put_resp.json().get("id")
                        uploaded_bytes += len(chunk)
                        break
                    elif put_resp.status_code == 308:
                        uploaded_bytes += len(chunk)
                    else:
                        raise RuntimeError(f"Chunk failed (HTTP {put_resp.status_code})")

            if vid_id:
                yt_url = f"https://youtu.be/{vid_id}"
                logger.info(f"✅ UPLOADED {label} TO YOUTUBE: {yt_url}")
                _append_upload_report(f"- 🎉 **LIVE ON YOUTUBE ({label})**: [{title}]({yt_url}) (`{yt_url}`)")
                return vid_id

        except Exception as up_err:
            logger.warning(f"Upload attempt {attempt}/3 warning: {up_err}")
            time.sleep(4)

    return None

def produce_news_episode(category="AUTO", is_short=True, is_breaking=False, anchor_gender=None, edition="auto", skip_upload=False):
    resolved_edition = get_current_edition() if edition == "auto" else edition.upper()
    cfg = EDITION_CONFIGS.get(resolved_edition, EDITION_CONFIGS[EDITION_MORNING])

    cleanup_temp_files()
    os.makedirs("output", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    script_data = generate_news_script(
        category=category, is_short=is_short, is_breaking=is_breaking,
        anchor_gender=anchor_gender, edition=resolved_edition,
    )
    resolved_cat = script_data.get("category", "NATION")
    language = script_data.get("language", "hindi")
    chosen_gender = script_data.get("anchor_gender", "female")
    scenes = script_data.get("scenes", [])

    scene_assets = []
    cumulative_sec = 0.0

    for idx, scene in enumerate(scenes):
        sid = idx + 1
        audio_path = f"temp/voice_{sid}.mp3"
        img_path = f"temp/scene_broll_{sid}.jpg"

        download_scene_image(
            prompt=scene.get("image_prompt", ""),
            output_path=img_path,
            is_short=is_short,
            search_query=scene.get("search_query", ""),
            rss_image_url=scene.get("rss_image_url", ""),
            headline_text=scene.get("headline_banner", ""),
            counter_text=scene.get("counter_text", f"ख़बर {sid}"),
            category_tag=scene.get("category_tag", "राष्ट्रीय" if idx % 2 == 0 else "अंतरराष्ट्रीय"),
            bulletin_label=scene.get("bulletin_label", cfg["bulletin_label"]),
            scene_idx=idx,
        )

        synthesize_broadcast_voice(
            text=scene.get("narration", ""),
            output_path=audio_path,
            category=resolved_cat,
            gender=chosen_gender,
            language=language,
        )
        dur = _get_audio_duration(audio_path)
        cumulative_sec += dur

        scene_assets.append({
            "scene_id": sid, "audio_path": audio_path, "image_path": img_path,
            "narration": scene.get("narration", ""),
            "subtitles": scene.get("subtitles", scene.get("narration", "")),
            "headline_banner": scene.get("headline_banner", script_data.get("headline_banner", "बड़ी ख़बर")),
            "camera_angle": "closeup" if idx % 2 == 1 else "wide",
        })

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "short" if is_short else f"long_{resolved_edition.lower()}"
    output_video = f"output/{prefix}_{resolved_cat.lower()}_{timestamp}.mp4"
    build_news_video(script_data=script_data, scene_assets=scene_assets, output_path=output_video, is_short=is_short)

    _mirror_video_for_github_artifacts(output_video, is_short=is_short)
    logger.info(f"🎉 Ready: {output_video} ({cumulative_sec/60.0:.2f} mins | {len(scene_assets)} Stories)")

    vid_id = None
    if not skip_upload:
        vid_id = upload_to_youtube(output_video, script_data, is_short=is_short)

    return output_video, vid_id

def main():
    parser = argparse.ArgumentParser(description="24/7 Autonomous AI TV News Studio Bot")
    parser.add_argument("--once", action="store_true", help="Run a single cycle and exit")
    parser.add_argument("--loop", action="store_true", help="Force infinite 24/7 loop even in CI")
    parser.add_argument("--type", choices=["short", "long", "both"], default="both", help="Video format")
    parser.add_argument("--edition", choices=["auto", "morning", "afternoon", "evening"], default="auto", help="Long video edition")
    parser.add_argument("--category", default="AUTO", help="NATION, WORLD, TECHNOLOGY, or AUTO")
    parser.add_argument("--anchor", choices=["male", "female", "auto"], default="auto", help="Anchor gender")
    parser.add_argument("--breaking", action="store_true", help="Breaking news mode")
    parser.add_argument("--skip-upload", action="store_true", help="Render locally without YouTube upload")
    parser.add_argument("--check-youtube", action="store_true", help="Only test YouTube OAuth credentials and exit")
    args = parser.parse_args()

    _ensure_system_fonts_on_ci()

    if args.check_youtube:
        ok = verify_youtube_credentials()
        sys.exit(0 if ok else 1)

    if not args.skip_upload:
        verify_youtube_credentials()

    anchor_override = None if args.anchor == "auto" else args.anchor
    is_ci = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
    run_once = args.once or (is_ci and not args.loop)

    if run_once:
        uploaded_ids = []
        if args.type in ("long", "both"):
            _, vid_l = produce_news_episode(
                category=args.category, is_short=False, is_breaking=args.breaking,
                anchor_gender=anchor_override, edition=args.edition, skip_upload=args.skip_upload,
            )
            if vid_l: uploaded_ids.append(("LONG", vid_l))
        if args.type in ("short", "both"):
            _, vid_s = produce_news_episode(
                category=args.category, is_short=True, is_breaking=args.breaking,
                anchor_gender=anchor_override, edition=args.edition, skip_upload=args.skip_upload,
            )
            if vid_s: uploaded_ids.append(("SHORT", vid_s))

        if uploaded_ids:
            for vtype, vid in uploaded_ids:
                logger.info(f"📺 {vtype} LIVE ON YOUTUBE: https://youtu.be/{vid}")
        return

    logger.info("📡 Starting 24/7 Autonomous TV News Loop...")
    while True:
        produce_news_episode(category=args.category, is_short=False, is_breaking=False, anchor_gender=anchor_override, edition=args.edition)
        produce_news_episode(category=args.category, is_short=True, is_breaking=False, anchor_gender=anchor_override, edition=args.edition)
        time.sleep(max(1, SHORTS_INTERVAL_HOURS) * 3600)

if __name__ == "__main__":
    main()
