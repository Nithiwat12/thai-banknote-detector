"""Bounded latest-frame camera reader; release on stop or inactivity."""
import os
import atexit
import threading
import time
import cv2

def frame_is_usable(frame):
    """Reject covered/near-uniform frames before inference, not denomination filtering."""
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    return float(gray.mean()) >= 8 and float(gray.std()) >= 4

class Camera:
    def __init__(self,index=0):
        self.cap=cv2.VideoCapture(index,cv2.CAP_DSHOW) if os.name=='nt' else cv2.VideoCapture(index)
        if not self.cap.isOpened() and os.name=='nt':
            self.cap.release();self.cap=cv2.VideoCapture(index)
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError('เปิดกล้องไม่ได้ ตรวจหมายเลขกล้องและปิดโปรแกรมอื่นที่ใช้กล้องอยู่')
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT,480)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE,1)
        self.cap.set(cv2.CAP_PROP_FPS,30)
        self.lock=threading.Lock();self.stop_event=threading.Event()
        self.frame=None;self.sequence=0;self.error=None;self.touch=time.monotonic()
        self.thread=threading.Thread(target=self._run,daemon=True)
        self.thread.start();atexit.register(self.close)

    def _run(self):
        try:
            while not self.stop_event.is_set():
                if time.monotonic()-self.touch > 30:
                    self.error='กล้องหยุดเพราะไม่มีการใช้งาน กรุณากดเริ่มใหม่';break
                ok,frame=self.cap.read()
                if not ok:
                    self.error='อ่านภาพจากกล้องไม่ได้';break
                with self.lock:
                    self.frame=frame;self.sequence+=1
                self.stop_event.wait(.005)
        except Exception as exc:
            self.error=str(exc)
        finally:
            self.cap.release()

    def read(self):
        self.touch=time.monotonic()
        with self.lock:
            return self.sequence,None if self.frame is None else self.frame.copy(),self.error

    def close(self):
        self.stop_event.set()
        if threading.current_thread() != self.thread:
            self.thread.join(timeout=1.)
        atexit.unregister(self.close)

class Video:
    def __init__(self,path):
        self.cap=cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            self.cap.release();raise RuntimeError('อ่านวิดีโอไม่ได้ ลองไฟล์ MP4 (H.264)')
        self.total=max(1,int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        self.sequence=0;self.lock=threading.Lock()
    def read(self):
        with self.lock:
            ok,frame=self.cap.read();self.sequence+=1
        return self.sequence,frame if ok else None,None if ok else 'วิดีโอจบหรืออ่านเฟรมต่อไม่ได้'
    def close(self):
        with self.lock:self.cap.release()


class InferenceWorker:
    """Single inference in flight, latest camera frame only, no Streamlit calls."""
    def __init__(self,source,infer,confidence):
        from stability import Stabilizer,AnnouncementGate,count_speech_text
        self.source,self.infer,self.confidence=source,infer,confidence
        self.stop_event=threading.Event();self.lock=threading.Lock()
        self.packet=None;self.error=None;self.touch=time.monotonic()
        self.stabilizer=Stabilizer(min_hits=3,min_seconds=.35,max_gap=3.)
        self.gate=AnnouncementGate(cooldown=1.5,hold=0.,formatter=count_speech_text)
        self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
    def _run(self):
        from stability import count_signature,count_speech_text
        last=-1;previous=None;old_conf=self.confidence
        try:
            while not self.stop_event.is_set():
                if time.monotonic()-self.touch>30:break
                seq,frame,error=self.source.read()
                if error:
                    with self.lock:self.error=error
                    break
                if frame is None or seq==last:
                    self.stop_event.wait(.01);continue
                last=seq;threshold=self.confidence
                if threshold!=old_conf:
                    self.stabilizer.tracks.clear()
                    from stability import AnnouncementGate
                    self.gate=AnnouncementGate(cooldown=1.5,hold=0.,formatter=count_speech_text);old_conf=threshold
                frame,ds,fps,quality=self.infer(frame,threshold)
                if self.stop_event.is_set():break
                now=time.monotonic()
                # Slow inference must not expire every track before confirmation.
                self.stabilizer.max_gap=max(3.,(now-previous)*1.5) if previous else 3.
                previous=now
                stable=self.stabilizer.update(ds,now);values=count_signature(ds)
                event=self.gate.update(values,now)
                with self.lock:
                    if event is None and self.packet and self.packet[6]==values:event=self.packet[-1]
                    self.packet=(seq,frame,ds,stable,fps,quality,values,event)
                self.stop_event.wait(.01)
        except Exception as exc:
            with self.lock:self.error=f'ประมวลผลไม่ได้: {exc}'
        finally:self.source.close()
    def read(self):
        self.touch=time.monotonic()
        with self.lock:
            packet=self.packet
            # Preserve an announcement until the UI consumes it.
            if packet and packet[-1]:self.packet=(*packet[:-1],None)
            return packet,self.error
    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=.2)
        self.source.close()

class BrowserFrames:
    """Bounded mailbox for browser frames. No camera or capture thread on server."""
    def __init__(self):
        self.lock=threading.Lock();self.sequence=-1;self.frame=None;self.closed=False
    def submit(self,sequence,frame):
        with self.lock:
            if not self.closed and sequence>self.sequence:
                self.sequence=sequence;self.frame=frame
    def read(self):
        with self.lock:return self.sequence,self.frame,None
    def close(self):
        with self.lock:self.closed=True;self.frame=None
