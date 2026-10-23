#!/usr/bin/env bash
# Päivittää Sisu Hockeyn HTML- ja JSON-julkaisun sekä puskee muutokset GitHubiin.
# Aja tästä repon juuresta tai cronista / n8n Execute Command -solmusta.
set -Eeuo pipefail

scheduled_run=false
case "${1:-}" in
  "") ;;
  --scheduled) scheduled_run=true ;;
  -h|--help)
    cat <<'EOF'
Käyttö: update_sisu.sh [--scheduled]

Ilman valintaa skripti päivittää ottelut heti. --scheduled-valinnalla
ma–pe ajetaan vain klo 07, 16 ja 20; la–su tasatunnein klo 08–22
(Europe/Helsinki).
EOF
    exit 0
    ;;
  *)
    echo "Tuntematon valinta: $1" >&2
    exit 2
    ;;
esac

if [[ "${scheduled_run}" == true ]]; then
  weekday="$(TZ=Europe/Helsinki date +%u)" # 1 = ma, 7 = su
  hour="$(TZ=Europe/Helsinki date +%H)"
  should_run=false

  if (( weekday <= 5 )); then
    case "${hour}" in
      07|16|20) should_run=true ;;
    esac
  elif (( 10#${hour} >= 8 && 10#${hour} <= 22 )); then
    should_run=true
  fi

  if [[ "${should_run}" != true ]]; then
    echo "Ajastettu haku ohitetaan: Helsinki-aika on viikonpäivä ${weekday}, klo ${hour}."
    exit 0
  fi
fi

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
