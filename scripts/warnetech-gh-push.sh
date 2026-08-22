#!/data/data/com.termux/files/usr/bin/bash
msg="${1:-update}"
git add .
git commit -m "$msg"
git push origin main
