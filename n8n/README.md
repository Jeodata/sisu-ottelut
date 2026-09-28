# n8n-työnkulku (vaihtoehto GitHub Actionsille)

Tuo tiedosto `sisu-ottelut.json` n8n:ään: **Workflows → Import from File**.

Työnkulku:

1. Ajastus **07:15, 16:15 ja 20:15** (Europe/Helsinki)
2. Hakee kauden ja ottelut Leijonat-tulospalvelun JSON-APIsta
3. Muotoilee `games.json`-tiedoston
4. Kirjoittaa sen GitHub-repoon (`docs/games.json`)

GitHub-solmuun tarvitaan n8n:n GitHub-tunniste (repo: `Jeodata/sisu-ottelut`).
HTML-sivu syntyy edelleen GitHub Actionsissa (`publish.py`), joten n8n riittää
JSON-päivitykseen. Jos n8n on ainoa automaatio, aja sen sijaan Python-skripti
n8n Execute Command -solmulla:

```bash
python3 publish.py --out docs && git add docs && git commit -m "ottelut" && git push
```
