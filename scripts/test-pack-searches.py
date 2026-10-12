#!/usr/bin/env python3
"""Exercise a fresh Prowlarr process with local, simulated indexers."""
import argparse
import copy
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--dotnet', default='dotnet')
    args = parser.parse_args()
    args.app = args.app.resolve()
    root = Path(tempfile.mkdtemp(prefix='prowlarr pack trial '))
    data = root / 'Data with spaces'
    data.mkdir()
    port = free_port()
    key = secrets.token_hex(16)
    queries = []
    titles = {'5000': 'Example.Series.S01-S03.1080p.WEB-DL',
              '2000': 'Example.Collection.Trilogy.2000-2002.1080p.BluRay'}
    (data / 'config.xml').write_text(
        f'<Config><BindAddress>127.0.0.1</BindAddress><Port>{port}</Port><ApiKey>{key}</ApiKey>'
        '<AuthenticationMethod>Forms</AuthenticationMethod>'
        '<AuthenticationRequired>DisabledForLocalAddresses</AuthenticationRequired>'
        '<LaunchBrowser>False</LaunchBrowser><AnalyticsEnabled>False</AnalyticsEnabled>'
        '<UpdateAutomatically>False</UpdateAutomatically><LogLevel>Debug</LogLevel></Config>')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            protocol, mode = parsed.path.strip('/').split('/')[:2]
            if query.get('t') == ['caps']:
                generic = 'no' if mode in ('specialized', 'title-only') else 'yes'
                specialized = 'no' if mode == 'generic' else 'yes'
                tv_params = 'title' if mode == 'title-only' else 'q,season,ep,tvdbid'
                movie = 'no' if mode in ('generic', 'title-only') else 'yes'
                body = (f'<caps><server version="1.0"/><limits max="100" default="100"/>'
                        f'<searching><search available="{generic}" supportedParams="q"/>'
                        f'<tv-search available="{specialized}" supportedParams="{tv_params}"/>'
                        f'<movie-search available="{movie}" supportedParams="q,imdbid,tmdbid"/>'
                        '</searching><categories><category id="5000" name="TV"/>'
                        '<category id="2000" name="Movies"/></categories></caps>')
            else:
                queries.append((protocol, mode, query))
                cat = '5000' if '5000' in query.get('cat', ['5000'])[0] else '2000'
                mime = 'application/x-bittorrent' if protocol == 'Torznab' else 'application/x-nzb'
                link = f'http://127.0.0.1:{self.server.server_port}/{protocol}/{mode}/release'
                body = (f'<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed" '
                        'xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/">'
                        '<channel><title>Simulated indexer</title><description>Local trial</description>'
                        f'<link>{link}</link><newznab:response offset="0" total="1"/><item>'
                        f'<title>{titles[cat]}</title><guid>{link}/{cat}</guid><link>{link}</link>'
                        f'<pubDate>{formatdate(usegmt=True)}</pubDate><category>{cat}</category>'
                        f'<enclosure url="{link}" length="123456789" type="{mime}"/>'
                        f'<torznab:attr name="category" value="{cat}"/>'
                        '<torznab:attr name="seeders" value="3"/><torznab:attr name="peers" value="5"/>'
                        f'<newznab:attr name="category" value="{cat}"/>'
                        '<newznab:attr name="size" value="123456789"/>'
                        '</item></channel></rss>')
            encoded = body.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/xml')
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    mock = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=mock.serve_forever, daemon=True).start()

    def request(path, payload=None, method=None, raw=False):
        req = Request(f'http://127.0.0.1:{port}/{path}',
                      data=None if payload is None else json.dumps(payload).encode(),
                      headers={'X-Api-Key': key, 'Content-Type': 'application/json'}, method=method)
        with urlopen(req, timeout=90) as response:
            body = response.read()
            return body if raw else json.loads(body) if body else None

    def api(path, payload=None, method=None):
        return request('api/v1/' + path, payload, method)

    process = None
    log = (root / 'host.log').open('a')

    def start():
        nonlocal process
        executable = [str(args.app)] if args.app.suffix.lower() == '.exe' else [args.dotnet, str(args.app)]
        process = subprocess.Popen([*executable, '-nobrowser', f'-data={data}'], stdout=log, stderr=subprocess.STDOUT)
        for _ in range(180):
            if process.poll() is not None:
                raise RuntimeError(f'Application exited; see {root / "host.log"}')
            try:
                api('system/status')
                return
            except (URLError, HTTPError):
                time.sleep(0.5)
        raise TimeoutError('Prowlarr did not start')

    def stop():
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    try:
        start()
        assert b'<html' in request('', raw=True).lower(), 'Packaged web interface is missing'
        schemas = api('indexer/schema')
        profile = api('appprofile')[0]['id']
        indexers = []
        for protocol in ('Torznab', 'Newznab'):
            for mode in ('both', 'generic', 'specialized', 'title-only'):
                body = copy.deepcopy(next(s for s in schemas if s['implementation'] == protocol))
                body.update(name=f'Trial {protocol} {mode}', enable=True, appProfileId=profile, priority=25, tags=[])
                values = {'baseUrl': f'http://127.0.0.1:{mock.server_port}',
                          'apiPath': f'/{protocol}/{mode}/api', 'apiKey': 'local-trial'}
                for field in body['fields']:
                    if field['name'] in values:
                        field['value'] = values[field['name']]
                created = api('indexer', body)
                indexers.append((created['id'], protocol, mode))

        for search_type, cat in (('tvpack', '5000'), ('moviepack', '2000'),
                                 ('tvsearch', '5000'), ('movie', '2000')):
            queries.clear()
            results = api('search?' + urlencode({'type': search_type, 'query': 'Example', 'categories': cat}))
            expected = 8 if cat == '5000' else 6
            assert len(results) == expected, f'{search_type}: expected {expected} indexers, got {len(results)}'
            assert all(r['title'] == titles[cat] for r in results)
            assert all(r['size'] == 123456789 for r in results)
            assert all(r.get('seeders') == 3 for r in results if r['protocol'] == 'torrent')
            for protocol, mode, query in queries:
                assert query['t'] == (['tvsearch' if cat == '5000' else 'movie'] if mode in ('specialized', 'title-only') else ['search']), (mode, query.get('t'))
                assert query['title' if mode == 'title-only' else 'q'] == ['Example']
                if mode == 'title-only':
                    assert 'q' not in query
                assert not {'season', 'ep', 'year', 'imdbid', 'tmdbid', 'tvdbid'}.intersection(query)

        # Sonarr/Radarr keep using standard Torznab/Newznab endpoints. Check
        # that their broad searches and RSS preserve the complete release.
        for indexer, protocol, mode in indexers:
            caps = ET.fromstring(request(f'{indexer}/api?t=caps', raw=True))
            assert caps.find('searching/search').get('available') == ('no' if mode in ('specialized', 'title-only') else 'yes')
            if mode == 'title-only':
                assert 'title' in caps.find('searching/tv-search').get('supportedParams').split(',')
            for cat in ('5000', '2000'):
                if mode == 'title-only' and cat == '2000':
                    continue
                kind = 'search' if mode == 'generic' else 'tvsearch' if cat == '5000' else 'movie'
                param = 'title' if mode == 'title-only' else 'q'
                queries.clear()
                xml = ET.fromstring(request(f'{indexer}/api?' + urlencode({'t': kind, 'cat': cat, param: 'Example'}), raw=True))
                item = xml.find('channel/item')
                assert item is not None and item.findtext('title') == titles[cat]
                assert f'127.0.0.1:{port}' in item.find('enclosure').get('url'), 'Download was not proxied'
                if mode == 'title-only':
                    assert queries and all(q.get('title') == ['Example'] and 'q' not in q for _, _, q in queries), 'TV title was lost in the proxy'

        try:
            api('search?' + urlencode({'type': 'tvpack', 'query': 'Example {Season:1}'}))
            raise AssertionError('Pack query accepted narrowing tokens')
        except HTTPError as error:
            assert error.code == 400

        queries.clear()
        api('search?' + urlencode({'type': 'tvsearch', 'query': 'Example {Season:2} {Episode:3}', 'indexerIds': indexers[0][0]}))
        assert any(q.get('season') in (['2'], ['02']) and q.get('ep') == ['3'] for _, _, q in queries), 'Ordinary episode search changed'
        stop()
        start()
        assert len(api('search?' + urlencode({'type': 'moviepack', 'query': 'Example'}))) == 6
        assert len(api('search?' + urlencode({'type': 'tvpack', 'query': 'Example'}))) == 8
        print('PASS: eight capability/protocol combinations, pack searches, standard proxy, metadata, ordinary searches and restart')
        print(f'Trial logs: {root}')
    finally:
        stop()
        log.close()
        mock.shutdown()
        mock.server_close()


if __name__ == '__main__':
    main()
