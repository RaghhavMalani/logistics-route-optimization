"""Loopback-only allowlisted evidence player; never serves private work state."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import mimetypes,re,sys

ROOT=Path(__file__).resolve().parents[1]/'work/ui-visual-upgrade-20261101'
IMAGES={'company-selected','company-selected-wide','fleet-review-actual','fleet-review-mixed','global-source','global-source-wide','global-comparison','global-route','global-globe','port-advisory','vessel-response','admin-source-quality','mobile-company-layers','mobile-company-timeline','mobile-global-comparison','mobile360-global-comparison'}


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self): self.deliver(False)
    def do_GET(self): self.deliver(True)
    def deliver(self,body):
        route=self.path.split('?',1)[0]
        direct={'/':ROOT/'evidence.html','/board.png':ROOT/'board.png','/video.mp4':ROOT/'video/ui-upgrade.mp4','/captions.vtt':ROOT/'video/captions.vtt'}
        target=direct.get(route)
        match=re.fullmatch(r'/(before|after)/([a-z0-9-]+)\.png',route)
        if match and match[2] in IMAGES: target=ROOT/match[1]/(match[2]+'.png')
        if target is None or not target.is_file(): self.send_error(404);return
        size=target.stat().st_size;start,end=0,size-1;status=200
        if self.headers.get('Range'):
            selected=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
            if not selected: self.send_error(416);return
            start=int(selected[1]);end=min(size-1,int(selected[2])) if selected[2] else size-1
            if start>end or start>=size: self.send_error(416);return
            status=206
        self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
        self.send_header('Content-Length',str(end-start+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        if not body:return
        try:
            with target.open('rb') as stream:
                stream.seek(start);remaining=end-start+1
                while remaining:
                    chunk=stream.read(min(65536,remaining));self.wfile.write(chunk);remaining-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):pass


if __name__=='__main__':
    port=int(sys.argv[1]) if len(sys.argv)>1 else 8922
    print(f'Local evidence: http://127.0.0.1:{port}/',flush=True)
    ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
