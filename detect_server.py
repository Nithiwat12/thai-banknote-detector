"""Tiny local HTTP endpoint: browser posts a JPEG, gets boxes + Thai speech text back.

Runs in a background thread of the Streamlit process so the camera loop never waits
for a Streamlit rerun. One request at a time per client (the browser awaits each reply).
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

from media import frame_is_usable
from stability import Detection, deduplicate, count_signature, count_speech_text

def make_detector(model, lock, class_values, device, imgsz=640):
    def detect(frame, threshold):
        t0 = time.perf_counter()
        if not frame_is_usable(frame):
            return [], 0., 'ภาพมืดหรือไม่มีรายละเอียดเพียงพอ กรุณาเพิ่มแสงและเล็งกล้องใหม่'
        with lock:
            r = model.predict(frame, conf=threshold, imgsz=imgsz, device=device,
                              max_det=30, verbose=False, save=False)[0]
        ds = []
        if r.boxes is not None:
            for b, c, s in zip(r.boxes.xyxy.cpu().tolist(), r.boxes.cls.cpu().tolist(), r.boxes.conf.cpu().tolist()):
                if int(c) in class_values:
                    ds.append(Detection(tuple(b), class_values[int(c)], float(s)))
        return deduplicate(ds), 1 / max(time.perf_counter() - t0, 1e-6), ''
    return detect

def build_response(frame, detect, conf):
    """Run detection on a BGR frame and return the JSON-able result the browser expects."""
    h, w = frame.shape[:2]
    ds, fps, quality = detect(frame, conf)
    return {
        'boxes': [{'box': [d.box[0]/w, d.box[1]/h, d.box[2]/w, d.box[3]/h],
                   'label': f'{d.value} THB {d.confidence:.2f}'} for d in ds],
        'text': count_speech_text(count_signature(ds)),
        'fps': round(fps, 1), 'quality': quality}

def start_server(detect, host='0.0.0.0'):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def _cors(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', '*')
            self.send_header('Access-Control-Allow-Private-Network', 'true')
        def _json(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
            self.send_response(code); self._cors()
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body))); self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_OPTIONS(self):
            self.send_response(204); self._cors(); self.end_headers()
        def do_GET(self):
            self._json(200, {'ok': True})
        def do_POST(self):
            try:
                n = int(self.headers.get('Content-Length', 0))
                if not 0 < n <= 3_000_000:
                    return self._json(400, {'error': 'bad size'})
                conf = float(parse_qs(urlparse(self.path).query).get('conf', ['0.4'])[0])
                conf = min(.95, max(.05, conf))
                frame = cv2.imdecode(np.frombuffer(self.rfile.read(n), np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    return self._json(400, {'error': 'bad image'})
                self._json(200, build_response(frame, detect, conf))
            except Exception as exc:
                self._json(500, {'error': str(exc)})
    server = ThreadingHTTPServer((host, 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]
