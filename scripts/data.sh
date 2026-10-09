#!/usr/bin/env bash
# Botun yaddaşı (data/ qovluğu) ayrıca "bot-data" budağında saxlanılır.
# Hər dəfə yalnız son vəziyyət saxlanılır, ona görə repozitoriya böyümür.
#
#   bash scripts/data.sh restore   # bot-data budağından data/ qovluğuna
#   bash scripts/data.sh save      # data/ qovluğunu bot-data budağına
set -euo pipefail

BRANCH="bot-data"
DIR="data"

case "${1:-}" in
  restore)
    mkdir -p "$DIR"
    if git ls-remote --exit-code --heads origin "$BRANCH" >/dev/null 2>&1; then
      git fetch -q --depth=1 origin "$BRANCH"
      git archive FETCH_HEAD | tar -x -C "$DIR"
      echo "Məlumatlar bərpa olundu: $(ls "$DIR" | tr '\n' ' ')"
    else
      echo "İlk işə salınma — məlumat budağı hələ yoxdur, sıfırdan başlanır."
    fi
    ;;
  save)
    if [ ! -d "$DIR" ] || [ -z "$(ls -A "$DIR")" ]; then
      echo "Saxlanacaq məlumat yoxdur."
      exit 0
    fi
    tmp="$(mktemp -d)"
    cp -r "$DIR"/. "$tmp"/
    cd "$tmp"
    git init -q -b "$BRANCH"
    git add -A
    git -c user.name="xeber-bot" \
        -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit -q -m "Bot məlumatları: $(date -u +%Y-%m-%dT%H:%MZ)"
    remote="${DATA_REMOTE:-https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git}"
    git push -q -f "$remote" "$BRANCH"
    echo "Məlumatlar saxlanıldı."
    ;;
  *)
    echo "İstifadə: bash scripts/data.sh restore|save" >&2
    exit 2
    ;;
esac
