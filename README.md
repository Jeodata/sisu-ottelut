# Sisu Hockey – päivän ottelut

Automaattinen, huoltovapaa ja julkinen ottelunäkymä **Sisu Hockey Hämeenlinna ry:n** (`AssID 11015646`) kaikkien joukkueiden otteluille. Järjestelmä palvelee samasta lähteestä sekä hallin **Raspberry Pi -infonäyttöä** että seuran verkkosivujen (**sisuhockey.fi**) otteluosiota.

* **Julkinen näkymä:** [https://jeodata.github.io/sisu-ottelut/](https://jeodata.github.io/sisu-ottelut/)
* **Seuran kotisivut:** [https://www.sisuhockey.fi/ottelut](https://www.sisuhockey.fi/ottelut)

---

## Mitä järjestelmä tuottaa

* **Mobiiliresponsiivinen HTML-sivu (`docs/index.html`):**
  * Näyttää päivän ottelut jaoteltuna tilan mukaan (*Käynnissä*, *Vielä pelaamatta*, *Valmistuneet*) sekä hiljaisina päivinä tulevat pelipäivät.
  * Sisältää automaattisen taustapäivityksen (5 min välein) ja välimuistin ohituksen (`?t=timestamp`), joka pitää Raspberry Pi -kioskinäytön jatkuvasti ajan tasalla ja kestää mahdolliset verkkokatkokset.
  * Sisältää `postMessage`-korkeusviestinnän (`sisu-height`), jonka avulla sivu mukautuu saumattomasti `iframe`-upotukseen seuran kotisivuilla.
* **Koneellisesti luettava JSON (`docs/games.json`, `docs/latest.json`)**
* **Päiväarkisto (`docs/archive/YYYY-MM-DD.json`)**

---

## Arkkitehtuuri ja riippuvuudet

### 1. Ohjelmistoriippuvuudet
* **Python 3.11+** (GitHub Actions ajaa versiolla **Python 3.12**).
* **Ei ulkoisia `pip`-kirjastoja:** Koko koodi (`sisu_ottelut.py`, `render_html.py`, `publish.py`) käyttää ainoastaan Pythonin standardikirjastoa (`urllib`, `json`, `datetime`, `zoneinfo`, `html`, `argparse`, `pathlib`).

### 2. Cloudflare Worker -välityspalvelin (Proxy)
Leijonat.fi-tulospalvelun CloudFront-palomuuri estää suoraan datakeskuksista (kuten GitHub Actions -palvelimilta) tulevat kutsut (`HTTP 403 Forbidden`). 
* Tämän kiertämiseksi `sisu_ottelut.py` reitittää API-kutsut **Cloudflare Worker** -välityspalvelimen (`https://leijonat-proxy.jeolehto.workers.dev`) kautta.
* Worker välittää kutsut `tulospalvelu.leijonat.fi`-rajapintaan puhtailla selainotsikoilla ja palauttaa JSON-vastauksen GitHub Actionsiin.

### 3. GitHub Actions -automaatio (`.github/workflows/update-games.yml`)
Päivitys pyörii täysin itsenäisesti GitHubin pilvessä ilman erillisiä palvelimia:
* **Viikonloppuisin (la–su):** 5 minuutin välein klo `05:00–20:55 UTC` (klo 07/08 – 22/23 Suomen aikaa).
* **Arkisin (ma–pe):** 3 kertaa päivässä (`05:15`, `15:15` ja `19:15 UTC`), jolloin näytön päivämäärä vaihtuu aamulla ja mahdolliset arki-/harjoitusottelut päivittyvät.
* **Manuaalinen / koodipäivitys:** Aina kun kooditiedostoja päivitetään `main`-haaraan tai työnkulku käynnistetään painikkeella (*Run workflow*).

*(Vaihtoehtoisesti mukana on myös `./cron/update_sisu.sh` ja `n8n/README.md`, mikäli päivitystä halutaan joskus ajaa omalla palvelimella tai n8n-automaatiolla).*

---

## Otteluiden tilalogiikka ja Leijonaliiga-automatiikka

Leijonat.fi-rajapinnan ottelutilat (`GameStatus`):
* `0` = Tulossa (*upcoming*)
* `1` = Käynnissä (*live*)
* `2` / `94` = Päättynyt (*finished*)

Koska junioriotteluissa `GameStatus` voi joskus jäädä nollaksi vaikka tulos on kirjattu, skripti merkitsee ottelun päättyneeksi myös silloin, kun `FinishedType >= 1`.

### Pikkujunnujen pelit (U8–U10 Leijonaliiga / pienpelit)
Pienempien junioreiden otteluissa ei käytetä reaaliaikaista tulospalvelua (`DeniedResults: true` / `SmallAreaGame: true`), minkä vuoksi Leijonat.fi jättää niiden tilaksi pysyvästi `0` (*Tulossa*). Jotta pelit eivät roiku koko päivää *Vielä pelaamatta* -listalla, `sisu_ottelut.py` ja `render_html.py` käyttävät kellonaikaan perustuvaa tilalogiikkaa:
1. **Ennen alkamisaikaa:** Ottelu näkyy **Tulossa**-osiossa ja näyttää alkamisajan (esim. `11:15`).
2. **0–50 min alkamisajasta:** Ottelu siirtyy automaattisesti **Käynnissä**-osioon ja tuloksen paikalla lukee vihreällä **`Pelataan`**.
3. **Yli 50 min alkamisajasta:** Ottelu siirtyy **Valmistuneet**-osioon ja tuloksen paikalla lukee **`Pelattu`** (ilman maalinumeroita tai voitto/tappio-väripalkkia).

---

## Paikallinen ajo ja kehitys

```bash
# Tulosta päivän ottelu-JSON komentoriville
python3 sisu_ottelut.py --pretty

# Rakenna HTML ja JSON-tiedostot docs/-kansioon (kuluva päivä)
python3 publish.py --out docs

# Rakenna tietyn päivän näkymä
python3 publish.py --date 2026-10-11 --out docs

Upotus verkkosivuille (sisuhockey.fi)
Näkymä on upotettu Yhdistysavaimen HTML-elementtiin automaattisesti skaalautuvalla iframe-koodilla:
<div style="width: 100%; max-width: 1000px; margin: 0 auto;">
  <iframe 
    id="sisu-ottelut-iframe"
    src="[https://jeodata.github.io/sisu-ottelut/](https://jeodata.github.io/sisu-ottelut/)" 
    width="100%" 
    onload="window.addEventListener('message', function(e){ if(e.data && e.data.type==='sisu-height' && e.data.height){ document.getElementById('sisu-ottelut-iframe').style.height = (e.data.height + 30) + 'px'; } });"
    style="width: 100%; height: 1850px; border: none; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); background: transparent; display: block;" 
    title="Sisu Hockey - Päivän ottelut">
  </iframe>
</div>

---

## Leijonat.fi JSON-API (tärkeimmät kutsut)
Endpoint                                                                                                          Käyttö
/helpers/getseasons                                                                                               käynnissä oleva kausi (SeasonNumber 2027 = kausi 2026–2027)
/helpers/getass?season=                                                                                           Seuraluettelo
/helpers/getteams?season=&assid=11015646                                                                          Sisu Hockeyn joukkueet
/helpers/getextsearchgames?season=&Filters[AssID]=11015646&Filters[StartDate]=&Filters[EndDate]=                  Seuran kaikkien joukkueiden ottelut valitulla aikavälillä
(Huom: Pääsivun /helpers/getgames palauttaa vain pääsarjat. Juniori- ja harrasteottelut haetaan aina getextsearchgames-kutsulla).


