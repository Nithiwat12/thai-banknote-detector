
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

from media import frame_is_usable
from stability import Detection, deduplicate, count_signature, count_speech_text, filter_candidates, ConfirmedFilter

def make_detector(model, lock, class_values, device, imgsz=640):
    def detect(frame, threshold):
        t0 = time.perf_counter()
        if not frame_is_usable(frame):
            return [], 0., 'ภาพมืดหรือไม่มีรายละเอียดเพียงพอ กรุณาเพิ่มแสงและเล็งกล้องใหม่'
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        if cv2.Laplacian(gray,cv2.CV_64F).var()<10:
            return [],0.,'ภาพไม่คมพอ กรุณาถือกล้องนิ่งและเพิ่มแสง'
        with lock:
            r = model.predict(frame, conf=threshold, imgsz=imgsz, device=device,
                              max_det=30, verbose=False, save=False)[0]
        ds = []
        if r.boxes is not None:
            for b, c, s in zip(r.boxes.xyxy.cpu().tolist(), r.boxes.cls.cpu().tolist(), r.boxes.conf.cpu().tolist()):
                if int(c) in class_values:
                    ds.append(Detection(tuple(b), class_values[int(c)], float(s)))
        return filter_candidates(ds,frame.shape,threshold), 1 / max(time.perf_counter() - t0, 1e-6), ''
    return detect

def build_response(frame, detect, conf, temporal=None, now=None):
    """Run detection on a BGR frame and return the JSON-able result the browser expects."""
    h, w = frame.shape[:2]
    ds, fps, quality = detect(frame, conf)
    ds=filter_candidates(ds,frame.shape,conf)
    if temporal is not None:
        ds,values,_=temporal.update(ds,frame.shape,conf,time.monotonic() if now is None else now)
    else:values=count_signature(ds)
    return {
        'boxes': [{'box': [d.box[0]/w, d.box[1]/h, d.box[2]/w, d.box[3]/h],
                   'label': f'{d.value} THB {d.confidence:.2f}'} for d in ds],
        'text': count_speech_text(values),
        'fps': round(fps, 1), 'quality': quality}

def start_server(detect, host='0.0.0.0'):
    states={}
    state_lock=threading.Lock()
    def stream_state(key):
        now=time.monotonic()
        with state_lock:
            for old in list(states):
                if now-states[old][2]>60:del states[old]
            if key not in states:
                if len(states)>=128:del states[min(states,key=lambda k:states[k][2])]
                states[key]=[ConfirmedFilter(),threading.Lock(),now]
            states[key][2]=now
            return states[key][:2]
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
                query=parse_qs(urlparse(self.path).query)
                conf = float(query.get('conf', ['0.6'])[0])
                key=query.get('stream',[''])[0]
                if not key or len(key)>200:return self._json(400,{'error':'missing camera stream id'})
                conf = min(.95, max(.60, conf))
                frame = cv2.imdecode(np.frombuffer(self.rfile.read(n), np.uint8), cv2.IMREAD_COLOR)
                if frame is None:
                    return self._json(400, {'error': 'bad image'})
                temporal,guard=stream_state(key)
                with guard:result=build_response(frame, detect, conf, temporal)
                self._json(200,result)
            except Exception as exc:
                self._json(500, {'error': str(exc)})
    server = ThreadingHTTPServer((host, 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]