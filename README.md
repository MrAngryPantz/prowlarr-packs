# Prowlarr Packs

This fork improves pack searches for [Sonarr Multi-Season](https://github.com/MrAngryPantz/sonarr-multiseason) and [Radarr Multi-Pack](https://github.com/MrAngryPantz/radarr-multipack). It remains compatible with ordinary Sonarr and Radarr installations.

In Search, open Query Options and choose **Multi-season packs** or **Movie packs**. Enter a series or collection title. Prowlarr uses each indexer's supported title search without restricting it to one episode, season or movie ID. TV and movie categories are selected automatically unless you choose categories yourself. Query limits, pagination, indexer priorities and category filters still apply.

The Newznab/Torznab proxy also fixes a title-search fallback: an indexer that supports only TV or movie text searches keeps that endpoint and its search title. TV indexers using `title` instead of `q` are supported, including those without episode or season filters. General text search is used only when supported. These fixes apply to the normal searches sent by Sonarr and Radarr as well as the new manual search modes.

## Using the four applications together

1. Connect Prowlarr to Sonarr and Radarr normally and synchronise your indexers.
2. Enable **Allow Multi-Season Packs** or **Allow Movie Packs** in the relevant Sonarr or Radarr quality profile. These options keep upgrades off.
3. Choose those profiles in [Seerr Packs](https://github.com/MrAngryPantz/seerr-packs), then request the seasons or collection movies you want.
4. Sonarr and Radarr decide whether a returned pack matches the monitored media and passes the normal quality and seeder checks. They handle the download and import.

Prowlarr does not need a special indexer protocol and does not change your seeder threshold. Existing RSS feeds and standard Torznab/Newznab requests continue to work. It preserves pack titles and release metadata, including download links, sizes and seeders.

Prowlarr's direct Download button sends a release to a download client. Use Sonarr or Radarr for automatic pack tracking and imports.

## Limits

A title search may return individual releases as well as packs. Prowlarr cannot prove which films or episodes a title contains; matching belongs to Sonarr and Radarr. An indexer that offers only IDs or RSS cannot provide a historical title search, and incomplete catalogues or ambiguous titles cannot be fixed by changing the proxy. No universal indexer coverage is claimed.

The new REST search types are `tvpack` and `moviepack`, for example `/api/v1/search?type=tvpack&query=Example`. They are Prowlarr search modes, not extra Torznab capabilities advertised to clients. Queries must contain a title without the structured ID, season, episode or year tokens.

## Build and test

Use the .NET SDK in `global.json`, Node.js 20 and Yarn 1.22.22.

```sh
yarn install --frozen-lockfile
yarn build --env production
dotnet build src/Prowlarr.sln -c Release
dotnet test src/Prowlarr.sln -c Release --no-build --no-restore --filter 'Category!=ManualTest&Category!=IntegrationTest&Category!=AutomationTest&Category!=WINDOWS'
ln -s ../UI _output/net8.0/UI
python3 scripts/test-pack-searches.py --app _output/net8.0/Prowlarr.dll
```

The isolated trial starts a fresh application with eight simulated indexers: Newznab and Torznab, each with general, specialised, combined and TV title-only search capabilities. It checks pack searches, normal proxy requests, preserved metadata, ordinary episode searches and a restart. It uses local test servers and never downloads real media or opens an existing database. Temporary logs are retained for inspection.

On Windows, run `scripts/build-windows.ps1` in PowerShell with the same build tools. It produces `_artifacts/prowlarr-packs-win-x64.zip`, including the web interface and .NET runtime. Extract it into its own folder and set `$env:PROWLARR__SERVER__PORT = '9697'` and start `Prowlarr.Console.exe -nobrowser -data=C:\ProwlarrPackTest`. Use a fresh data directory and a different port from your normal installation. The package does not install a Windows service automatically.

The compatibility workflow runs the unit suites and isolated trials on Linux and Windows. Manual tests and tests that require external services are excluded. This is an experimental fork; test separately before migrating an existing installation.

Prowlarr is developed by [the Prowlarr project](https://github.com/Prowlarr/Prowlarr). Upstream history, copyright notices and the [GPL v3 licence](LICENSE) are retained.
