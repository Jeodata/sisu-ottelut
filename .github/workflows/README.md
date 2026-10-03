# GitHub Actions -huomio

`update-games.yml` on jätetty repoihin dokumentointia ja manuaalista
diagnoosia varten, mutta se on GitHubissa pois käytöstä. Leijonat-tulospalvelun
CloudFront palauttaa GitHub-hosted runnereille HTTP 403:n, joten ajastus tehdään
`cron/update_sisu.sh`-skriptillä n8n:ssä, cronissa tai Manus-ajastuksella.

HTML- ja JSON-tiedostot pusketaan GitHubiin, ja GitHub Pages julkaisee `docs/`-
kansion normaalisti.
