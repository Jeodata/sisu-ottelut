# n8n-työnkulku / cron

Tiedosto `sisu-ottelut.json` on n8n:n **self-hosted**-asennukseen tarkoitettu
ajastus. Se ajaa klo **07:15, 16:15 ja 20:15 Europe/Helsinki** saman
`cron/update_sisu.sh`-skriptin, joka:

1. hakee Leijonat-tulospalvelun JSON-APIsta päivän ottelut,
2. renderöi `docs/index.html`-korttinäkymän sekä `docs/games.json`-tiedoston,
3. arkistoi päivän JSONin ja puskee muutokset GitHubiin.

## n8n:n käyttöönotto

1. Kloonaa repo n8n-palvelimelle, esimerkiksi `/opt/sisu-ottelut`.
2. Varmista, että palvelimella on `python3`, `git` ja toimiva GitHub SSH-/HTTPS-todennus.
3. Aja kerran:

   ```bash
   cd /opt/sisu-ottelut
   chmod +x cron/update_sisu.sh
   ./cron/update_sisu.sh
   ```

4. Tuo `sisu-ottelut.json`: **Workflows → Import from File**.
5. Jos repon polku on muu kuin `/opt/sisu-ottelut`, muuta solmun **Hae, renderöi ja puske GitHubiin** komentoa.
6. Aktivoi työnkulku.

> n8n Cloud ei yleensä salli Execute Command -solmua. Käytä silloin pientä VPS-/NAS-/Docker-n8n-asennusta tai järjestelmän cronia alla.

## Kevyt järjestelmä-cron

```cron
# Europe/Helsinki-ajastuksella toimivassa palvelimessa
15 7,16,20 * * * /opt/sisu-ottelut/cron/update_sisu.sh >> /var/log/sisu-ottelut.log 2>&1
```

Jos palvelimen cron käyttää UTC:tä, säädä ajat kesä-/talviajan mukaan tai käytä n8n:n `Europe/Helsinki`-aikavyöhykettä.

## GitHub Pages

Kun GitHub Pages on asetettu käyttämään `main`-haaran `/docs`-kansiota, jokainen
push julkaisee HTML:n ja JSON:n automaattisesti osoitteeseen
`https://jeodata.github.io/sisu-ottelut/`.
