name: 24/7 AI News Studio Bot

on:
  schedule:
    - cron: '0 */3 * * *'
  workflow_dispatch:

jobs:
  run-news-bot:
    runs-on: ubuntu-latest
    timeout-minutes: 45

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'

      - name: Install System Dependencies (FFmpeg & Hindi/English Fonts)
        run: |
          sudo apt-get update
          sudo apt-get install -y ffmpeg fonts-noto-core fonts-dejavu-core

      - name: Install Python Requirements
        run: |
          pip install --upgrade pip
          pip install edge-tts gTTS requests Pillow numpy google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2

      - name: Run News Studio Bot & Upload to YouTube (Short + Long)
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          YT_CLIENT_ID: ${{ secrets.YT_CLIENT_ID }}
          YT_CLIENT_SECRET: ${{ secrets.YT_CLIENT_SECRET }}
          YT_REFRESH_TOKEN: ${{ secrets.YT_REFRESH_TOKEN }}
        run: |
          python -u main.py --once --type both

      - name: Save Generated Video Artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: generated-news-videos
          path: |
            output/*.mp4
            final_short.mp4
            final_long.mp4
          retention-days: 3
