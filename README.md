# Sisu Hockey – päivän ottelut

Automaattinen, julkinen näkymä **Sisu Hockey Hämeenlinna ry**:n kaikkien
joukkueiden otteluille. Data tulee suoraan
[tulospalvelu.leijonat.fi](https://tulospalvelu.leijonat.fi/) JSON-APIsta
(ei DOM-raapimista).

Seura: **AssID `11015646`**.

## Mitä syntyy

- mobiiliresponsiivinen HTML-korttisivu (`docs/index.html`)
- koneellisesti luettava JSON (`docs/games.json`, `docs/latest.json`)
- päiväarkisto (`docs/archive/YYYY-MM-DD.json`)

Aamulla sivu näyttää päivän otteluohjelman. Iltapäivällä ja illalla samat
kortit päivittyvät valmistuneilla tuloksilla (`Päättynyt`, maalit, JA/VL).

## Paikallinen ajo

Python 3.11+, ei riippuvuuksia.

```bash
python3 sisu_ottelut.py --pretty          # JSON stdoutiin
python3 publish.py --out docs             # HTML + JSON docs/
python3 publish.py --date 2026-10-03 --out docs
```

## Automaatio (suositus): GitHub Actions + Pages

Repo sisältää työnkulun `.github/workflows/update-games.yml`:

| Aika (UTC) | Tarkoitus |
|---|---|
| 04:15 ja 06:15 | Aamun otteluohjelma (kattaa Helsingin kesä- ja talviajan) |
| 12:15, 14:15, 17:15, 19:15 | Iltapäivän ja illan tulospäivitykset |

Jokainen ajo hakee datan, kirjoittaa `docs/` ja julkaisee GitHub Pagesiin.

Ensimmäisen pushin jälkeen:

1. GitHub → **Settings → Pages**
2. Source: **GitHub Actions**
3. Julkinen osoite: `https://jeodata.github.io/sisu-ottelut/`

Työnkulun voi myös käynnistää manuaalisesti: **Actions → Päivitä Sisu Hockeyn ottelut → Run workflow**.

## Vaihtoehto: n8n

Tuo [`n8n/sisu-ottelut.json`](n8n/sisu-ottelut.json) n8n:ään
(ajat 07:15 / 16:15 / 20:15 Europe/Helsinki). Ohje: [`n8n/README.md`](n8n/README.md).

GitHub Actions on ensisijainen julkaisuputki, koska se generoi sekä HTML:n
että JSON:in ilman erillistä palvelinta.

## API (tärkeimmät kutsut)

| Endpoint | Käyttö |
|---|---|
| `/helpers/getseasons` | Käynnissä oleva kausi (`SeasonNumber` 2027 = 2026–2027) |
| `/helpers/getass?season=` | Seuraluettelo |
| `/helpers/getteams?season=&assid=` | Seuran joukkueet |
| `/helpers/getextsearchgames?season=&Filters[AssID]=11015646&Filters[StartDate]=&Filters[EndDate]=` | Kaikkien joukkueiden ottelut |

Pääsivun `/helpers/getgames` palauttaa vain pääsarjat. Juniori- ja
harrasteottelut haetaan `getextsearchgames`-kutsulla.

`GameStatus`: `0` ei alkanut, `1` käynnissä, `2` / `94` päättynyt.
Junioriotteluissa `GameStatus` voi jäädä nollaksi vaikka tulos on kirjattu
(`FinishedType >= 1`) — skripti merkitsee nämä päättyneiksi.
