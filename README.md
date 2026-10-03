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

## Automaatio: cron tai self-hosted n8n

Leijonat-tulospalvelun CloudFront-suoja estää GitHub-hosted runnerien pyynnöt
(HTTP 403), joten tiedonhaku ajetaan luotettavasti ympäristössä, jossa API on
sallittu: n8n-palvelimella, NAS:lla, VPS:llä tai Manus-ajastuksella. Julkaisu
pysyy GitHub-repossa ja GitHub Pagesissa.

Valmis komentosarja:

```bash
./cron/update_sisu.sh
```

Se lukitsee päällekkäiset ajot, synkronoi repon, muodostaa HTML:n + JSON:n ja
puskee vain muuttuneet `docs/`-tiedostot GitHubiin.

Valmis n8n-tuonti ja cron-ohjeet ovat [`n8n/README.md`](n8n/README.md).

### Ajastus

Aja komentosarja **klo 07:15, 16:15 ja 20:15 Europe/Helsinki**:

```cron
15 7,16,20 * * * /opt/sisu-ottelut/cron/update_sisu.sh >> /var/log/sisu-ottelut.log 2>&1
```

n8n-tuonti sisältää saman aikataulun ja Helsinki-aikavyöhykkeen.

### GitHub Pages (kertatoimi)

Repo on julkinen: https://github.com/Jeodata/sisu-ottelut

Ota Pages käyttöön kerran GitHubissa:

1. Avaa https://github.com/Jeodata/sisu-ottelut/settings/pages
2. **Build and deployment → Source:** Deploy from a branch
3. Branch: `main`, folder: `/docs` → **Save**
4. Julkinen osoite on tämän jälkeen https://jeodata.github.io/sisu-ottelut/

Ajastetut pushit julkaistaan sen jälkeen automaattisesti. Tässä ympäristössä
käytössä oleva GitHub-token voi luoda repon ja puskea tiedostoja, mutta sillä ei
ole Pages-asetuksen hallintaoikeutta.

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
