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
(Huom: getextsearchgames pysyy varsinaisena seuran otteluhaun lähteenä. getgames palauttaa oikeat julkiset GameID-arvot, kun valitaan sopiva subSerieId, ja sitä käytetään vain linkkien täsmäytykseen.)




## Ottelulinkit (PWA) – automaattinen täsmäytys

`getextsearchgames`-rajapinnan `GameID` **ei ole luotettava julkisen pelisivun gameid**.
Julkaisu käyttää `game_link_overrides.json`-tiedoston kausikohtaisia vahvistettuja vastaavuuksia
sekä API:n erikseen tarjoamia julkisia ottelutunnisteita, mikäli niitä on.

Jos julkista ottelutunnistetta ei tunneta, ottelukortti avaa varmuuden vuoksi
Leijonien tulospalvelun etusivun, ei väärän ottelun sivua.
Lisää manuaalisesti vahvistetut vastaavuudet `game_link_overrides.json`-tiedostoon
muodossa `"kausi": {"sisäinen_id": julkinen_id}`.

Esimerkiksi kaudelle 2027: `732527 -> 2721476` ja `735159 -> 2727976`.


### Uusi automaattinen ID-täsmäytys

`public_game_ids.py` hakee Leijonien `/helpers/getgames`-rajapinnasta ottelulistoja.
Tuloksissa `Games[*].GameID` on sivulla toimiva julkinen ottelutunniste
(esimerkiksi 2721476), kun taas vanhan `getextsearchgames`-haun tunniste voi
olla 732527. Linkki hyväksytään **vain**, kun päivämäärä, alkamisaika,
ottelujoukkueiden tunnisteet (tai puuttuvien tunnisteiden tapauksessa molemmat
joukkueiden lyhennenimet) sekä saatavilla oleva sarjataso täsmäävät
**yksiselitteisesti**.

Palvelun muutoin toimivaan datahakuun ei kosketa. Jokaisen julkaisuajon
alussa linkittäjä lukee julkaisukansion `public_game_ids.json`-välimuistin.
Vahvistetut julkiset tunnisteet tallennetaan sinne. Kun ottelulista ei palauta
yksiselitteistä julkista ID:tä, käytetään edelleen alkuperäistä turvallista
etusivulinkkiä. Tunnisteita **ei lasketa** vanhasta numerosta.

`getgames`-rajapinnan yleishaku ei välttämättä sisällä kaikkia juniorisarjoja.
Jos legacy-lähde sisältää `SubSerieID`-kentän, sitä kokeillaan. Lisäksi kauden
2027 U16 Suomi-sarjan varmistettu `subSerieId=4135` on mukana varatietona.
Muita sarjoja varten linkittäjä kokeilee joukkue- ja sarjatasohakua. Näiden
hakujen toimivuutta ei ole voitu todentaa kaikissa sarjoissa ilman live-APIa,
joten kaikkien ikäluokkien suoraa linkitystä ei vielä voida taata. Yhden
ajokerran uudet getgames-haut on rajoitettu 16 pyyntöön, jotta 5 minuutin
ajastettu päivitys ei kuormitu kohtuuttomasti.

Paikallisesti varmista regressiotesteillä:

```bash
python3 -m unittest discover -s tests -v
```

Julkaisu päivittyy vasta, kun muutokset viedään GitHubin `main`-haaraan.
Live-API-testit kannattaa tehdä vasta GitHub Actions -ympäristössä nykyisen
Cloudflare-proxyn kautta.

### Julkisten Leijonat-ottelulinkkien täsmäytys (23.10.2026)

`helpers/getextsearchgames` palauttaa sisäisen `GameID`-tunnisteen ja oman
`LevelID`-numerointinsa. Niitä **ei** voi käyttää sellaisenaan `game?gameid=`-
linkeissä tai verrata `helpers/getgames`-vastauksen `LevelID`-numeroihin.
Esimerkiksi U16-ottelun sisäinen `GameID=732527`, sisäinen `LevelID=1138`
sekä julkinen `GameID=2721476`, julkinen `LevelID=90` tarkoittavat samaa ottelua.

`public_game_ids.py` käyttää ensisijaisesti `getgames`-rajapinnan ottelulistaa,
rajattuna päivällä ja SiSun joukkueen `teamid`-tunnisteella. Vastaukset
kohdistetaan *molempien joukkueiden ID:llä, päivämäärällä ja alkamisajalla*.
Vain yksiselitteisestä vastaavuudesta muodostetaan julkinen URL; muuten
käytetään turvallisesti tulospalvelun etusivua. Vahvistetut tunnisteet
säilyvät `docs/public_game_ids.json`-välimuistissa seuraavia ajoja varten.

GitHub Actionsin **Hae ottelut ja rakenna sivu** -vaiheen loki näyttää
`Julkiset ottelulinkit: X/Y (hakupyyntoja N, ratkaisematta M)` sekä enintään
12 ratkaisemattoman ottelun sisäiset tunnisteet. Jos jokin ottelu edelleen
avaa etusivun, tarkista lokista kyseinen päivä ja `SisuTeamID` sekä pyynnön
saatavuus Cloudflare Workerin kautta. Joidenkin sarjojen `getgames`-suodatus
voi vaatia lisäselvitystä; mitään julkista ID:tä ei arvata.
