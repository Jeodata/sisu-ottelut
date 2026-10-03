#!/usr/bin/env bash
# Päivittää Sisu Hockeyn HTML- ja JSON-julkaisun sekä puskee muutokset GitHubiin.
# Aja tästä repon juuresta tai cronista / n8n Execute Command -solmusta.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK_FILE="${TMPDIR:-/tmp}/sisu-ottelut-update.lock"

# Estä päällekkäiset ajot (esim. manuaalinen ajo samaan aikaan cronin kanssa).
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "Päivitys on jo käynnissä — ohitetaan."
  exit 0
fi

cd "${ROOT}"

git fetch origin main
git pull --ff-only origin main
python3 publish.py --out docs

git add docs
if git diff --cached --quiet; then
  echo "Ei julkaistavia muutoksia."
  exit 0
fi

git -c user.name="${GIT_AUTHOR_NAME:-sisu-ottelut-bot}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-41898282+github-actions[bot]@users.noreply.github.com}" \
    commit -m "Päivitä Sisu Hockeyn ottelut $(date -u +%Y-%m-%dT%H:%MZ)"
git push origin main

echo "Julkaisu päivitetty onnistuneesti."
