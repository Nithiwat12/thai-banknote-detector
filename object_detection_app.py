from pathlib import Path
import base64
import os
import tempfile
import threading
import time
import uuid
import math
from collections import Counter
import imageio_ffmpeg
import torch
import cv2
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageOps
from ultralytics import YOLO
from stability import (Detection, DENOMINATIONS, Stabilizer, AnnouncementGate,
                       deduplicate, signature, speech_text, count_signature, count_speech_text)
from media import Video, frame_is_usable, InferenceWorker
from detect_server import make_detector, start_server, build_response

ROOT = Path(__file__).resolve().parent
MODEL_PATH = Path(os.environ.get('BANKNOTE_MODEL',str(ROOT/'best v26n.pt'))).expanduser()
st.set_page_config(page_title='ตรวจจับธนบัตรไทย',page_icon='💵',layout='wide')
speech = components.declare_component('banknote_speech',path=str(ROOT/'speech_component'))

@st.cache_resource
def load_model(path,stamp):
    torch.set_num_threads(max(1,min(4,os.cpu_count() or 1)))
    model=YOLO(path)
    names=model.names
    mapping={}
    for key,name in (names.items() if isinstance(names,dict) else enumerate(names)):
        clean=str(name).strip().lower().replace('บาท','').replace('baht','').replace(',','').strip()
        if clean not in {'20','50','100','500','1000'}:
            raise ValueError(f'ชื่อคลาสไม่ใช่ชนิดธนบัตรที่รองรับ: {key}={name}')
        mapping[int(key)]=int(clean)
    if set(mapping.values())!=set(DENOMINATIONS):
        raise ValueError('โมเดลต้องมีธนบัตรครบ 20/50/100/500/1000 บาท')
    return model,threading.Lock(),mapping

class Session:
    def __init__(self):
        self.worker=None;self.source=None;self.temp=None;self.image=None;self.status='พร้อมใช้งาน'
        self.rows=[];self.current='';self.event='';self.sequence=0;self.quality=''
        self.camera_boxes=[];self.reset_id=0;self.video=None;self.video_events=[];self.video_id=0;self.relay=None;self.relay_seq=0;self.token=uuid.uuid4().hex;self.last_frame=-1;self.fps=0.
        self.stabilizer=Stabilizer();self.gate=AnnouncementGate()
    def reset(self,bump=True):
        if bump:self.reset_id+=1
        self.camera_boxes=[]
        if self.worker is not None:self.worker.close();self.worker=None
        elif self.source is not None:self.source.close()
        self.source=None
        if self.temp is not None:self.temp.cleanup();self.temp=None
        self.video=None;self.video_events=[];self.relay=None;self.relay_seq=0;self.image=None;self.rows=[];self.current='';self.event='';self.sequence+=1;self.quality=''
        self.last_frame=-1;self.fps=0.;self.stabilizer=Stabilizer();self.gate=AnnouncementGate()
    def __del__(self):
        try:self.reset()
        except Exception:pass

if 'runtime' not in st.session_state:st.session_state.runtime=Session()
s=st.session_state.runtime
st.title('💵 ตรวจจับธนบัตรไทยพร้อมเสียง')
st.caption('20 • 50 • 100 • 500 • 1,000 บาท | ติ๊กเปิดกล้อง ระบบตรวจจับเรียลไทม์และพูดอัตโนมัติ')
try:
    if not MODEL_PATH.is_file():raise FileNotFoundError(f'ไม่พบโมเดล: {MODEL_PATH}')
    with st.spinner('กำลังโหลดโมเดล...'):
        model,model_lock,class_values=load_model(str(MODEL_PATH),MODEL_PATH.stat().st_mtime_ns)
except Exception as exc:
    st.error(f'โหลดโมเดลไม่สำเร็จ: {exc}')
    st.info('ติดตั้ง requirements.txt แล้วตรวจว่า best v26n.pt อยู่ข้างไฟล์แอป')
    st.stop()

conf=st.slider('ความมั่นใจขั้นต่ำ',.20,.90,.40,.05)
imgsz=640
device=0 if torch.cuda.is_available() else 'cpu'
# Changing confidence applies to the next inference without restarting the camera.
if s.worker is not None:s.worker.confidence=conf


@st.cache_resource
def get_detector(_model,_lock,_values,_device,stamp):
    # Browser camera frames go straight to this local endpoint (no Streamlit rerun per frame).
    detect=make_detector(_model,_lock,_values,_device)
    return start_server(detect),detect
detector_port,detect_frame=get_detector(model,model_lock,class_values,device,MODEL_PATH.stat().st_mtime_ns)
# BANKNOTE_RELAY=1 forces the slower Streamlit relay path (used automatically when the port is unreachable).
if os.environ.get('BANKNOTE_RELAY'):detector_port=0


def infer(frame, threshold=None):
    start=time.perf_counter()
    quality=''
    if not frame_is_usable(frame):
        quality='ภาพมืดหรือไม่มีรายละเอียดเพียงพอ กรุณาเพิ่มแสงและเล็งกล้องใหม่'
        return frame,[],0.,quality
    h,w=frame.shape[:2]
    if max(h,w)>1280:
        scale=1280/max(h,w);frame=cv2.resize(frame,(round(w*scale),round(h*scale)))
    with model_lock:
        r=model.predict(frame,conf=conf if threshold is None else threshold,imgsz=imgsz,device=device,
                        max_det=30,verbose=False,save=False)[0]
    detections=[]
    if r.boxes is not None:
        for b,cls,score in zip(r.boxes.xyxy.cpu().tolist(),r.boxes.cls.cpu().tolist(),r.boxes.conf.cpu().tolist()):
            if int(cls) in class_values:
                detections.append(Detection(tuple(b),class_values[int(cls)],float(score)))
    return frame,deduplicate(detections),1/max(time.perf_counter()-start,.000001),quality

def draw(frame,raw,stable):
    out=frame.copy()
    for ds,color in [(raw,(150,150,150)),(stable,(50,190,50))]:
        for d in ds:
            x1,y1,x2,y2=[int(v) for v in d.box]
            cv2.rectangle(out,(x1,y1),(x2,y2),color,2)
            cv2.putText(out,f'{d.value} THB {d.confidence:.2f}',(max(0,x1),max(18,y1-6)),
                        cv2.FONT_HERSHEY_SIMPLEX,.6,color,2,cv2.LINE_AA)
    return cv2.cvtColor(out,cv2.COLOR_BGR2RGB)

def process_video(uploaded):
    """Detect on the whole uploaded video, then render a playable MP4 with the boxes drawn on it.
    (Showing frames one by one with st.image flickers and cannot be played back.)"""
    s.temp=tempfile.TemporaryDirectory(prefix='banknote_')
    src=Path(s.temp.name)/('input'+Path(uploaded.name).suffix.lower())
    src.write_bytes(uploaded.getbuffer())
    cap=cv2.VideoCapture(str(src))
    if not cap.isOpened():
        cap.release();raise RuntimeError('อ่านวิดีโอไม่ได้ ลองไฟล์ MP4 (H.264)')
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS)
    if not (0<fps<=120):fps=25.
    stride=max(1,math.ceil(total/600)) if total>0 else 1   # at most ~600 frames are run through the model
    out=Path(s.temp.name)/'result.mp4'
    bar=st.progress(0.,text='กำลังตรวจวิดีโอ...')
    writer=None;last=[];signatures=Counter();idx=0;max_frames=1800
    # Speech events {t: seconds into the video, text}: the browser speaks them while the video plays.
    events=[];recent=[];last_text='';last_seen=-9.;last_event=-9.
    window=7 if stride==1 else 3;need=3 if stride==1 else 2   # smooth over recent frames so one misread frame is not spoken
    try:
        while idx<max_frames:
            ok,frame=cap.read()
            if not ok:break
            h,w=frame.shape[:2]
            if max(h,w)>1280:
                k=1280/max(h,w);frame=cv2.resize(frame,(round(w*k),round(h*k)))
            h,w=frame.shape[0]//2*2,frame.shape[1]//2*2;frame=frame[:h,:w]
            if idx%stride==0:
                frame,ds,s.fps,s.quality=infer(frame,conf)
                if ds:last=ds;signatures[count_signature(ds)]+=1
                else:last=[]
                t=idx/fps;recent.append(count_signature(ds) if ds else ());recent=recent[-window:]
                sig,votes=Counter(recent).most_common(1)[0]
                if sig and votes>=need:
                    last_seen=t;text=count_speech_text(sig)
                    if text!=last_text and t-last_event>=1.2:   # too soon after the last announcement: try again later
                        last_event=t;events.append({'t':round(t,2),'text':text});last_text=text
                elif not sig and t-last_seen>1.5:last_text=''
            if writer is None:
                writer=imageio_ffmpeg.write_frames(str(out),(w,h),fps=fps,codec='libx264',pix_fmt_in='rgb24',
                                                   pix_fmt_out='yuv420p',macro_block_size=1,quality=6,
                                                   output_params=['-movflags','+faststart']);writer.send(None)
            writer.send(np.ascontiguousarray(draw(frame,[],last)).tobytes())
            idx+=1
            if idx%5==0:bar.progress(min(.99,idx/(total if total>0 else 300)),text=f'กำลังตรวจวิดีโอ... {idx} เฟรม')
    finally:
        cap.release()
        if writer is not None:writer.close()
        bar.empty()
    if idx==0 or not out.is_file():raise RuntimeError('อ่านเฟรมจากวิดีโอไม่ได้')
    s.video=out.read_bytes();s.video_events=events;s.video_id+=1
    if signatures:
        best=signatures.most_common(1)[0][0]   # most frequent result across the video
        s.rows=[{'ชนิด (บาท)':value,'ความมั่นใจ':0.} for value,count in best for _ in range(count)]
        s.current=count_speech_text(best)
        s.status=f'ตรวจวิดีโอเสร็จ ({idx} เฟรม) กดเล่นวิดีโอ ระบบจะพูดตามที่ตรวจพบ'
    else:s.status=f'ตรวจวิดีโอเสร็จ ({idx} เฟรม) ไม่พบธนบัตรที่ผ่านเกณฑ์'

uploaded=st.file_uploader('อัปโหลดรูปภาพหรือวิดีโอ',type=['jpg','jpeg','png','webp','mp4','avi','mov','mkv','webm','m4v'])
start_file=st.button('ตรวจไฟล์ที่อัปโหลด',type='primary',disabled=uploaded is None,use_container_width=True)
if start_file:
    s.reset()
    try:
        if Path(uploaded.name).suffix.lower() in {'.jpg','.jpeg','.png','.webp'}:
            with Image.open(uploaded) as original:
                rgb=ImageOps.exif_transpose(original).convert('RGB');rgb.thumbnail((1280,1280))
                frame=cv2.cvtColor(np.array(rgb),cv2.COLOR_RGB2BGR)
            frame,ds,s.fps,s.quality=infer(frame,conf);s.image=draw(frame,[],ds)
            s.rows=[{'ชนิด (บาท)':d.value,'ความมั่นใจ':round(d.confidence,3)} for d in ds]
            s.current=count_speech_text(count_signature(ds));s.event=s.current;s.sequence+=1
            s.status='ผลภาพนิ่ง' if ds else 'ไม่พบธนบัตรที่ผ่านเกณฑ์'
        else:process_video(uploaded)
    except Exception as exc:s.reset();s.status=f'เริ่มไม่ได้: {exc}'

@st.fragment(run_every=.1 if s.worker is not None else None)
def live_panel():
    # Fixed layout: every element below always exists (empty slots when unused). A layout that
    # changes size between reruns makes Streamlit's frontend fail with "Bad delta path index".
    can_stop=s.worker is not None or s.image is not None or s.video is not None
    if st.button('หยุด / ล้างผล',key='stop',disabled=not can_stop):
        s.reset();s.status='หยุดแล้ว';st.rerun()  # full rerun so the video above is cleared too
    speech_box=st.container()
    status_slot,warn_slot,image_slot,fps_slot,table_slot,ok_slot=(st.empty() for _ in range(6))
    if s.worker is not None:
        packet,error=s.worker.read()
        if packet is not None and packet[0]!=s.last_frame:
            seq,frame,ds,stable,s.fps,s.quality,values,event=packet
            s.last_frame=seq;s.current=count_speech_text(values)
            # Retain the last event until another event or reset; sequence deduplicates it.
            if event:s.event=event;s.sequence+=1
            s.image=draw(frame,ds,stable)
            s.rows=[{'ชนิด (บาท)':d.value,'ความมั่นใจ':round(d.confidence,3)} for d in ds]
            s.status='ยืนยันผลต่อเนื่องแล้ว' if stable else ('พบธนบัตรแล้ว' if ds else 'ไม่พบธนบัตรที่ผ่านเกณฑ์ ลองขยับให้ชัดหรือปรับความมั่นใจ')
        if error:
            s.worker.close();s.worker=None;s.source=None
            s.current='';s.event='';s.sequence+=1;s.status=error
    session_key=f'{s.token}:{s.reset_id}'
    with speech_box:message=speech(reset_id=session_key,current_text=s.current,event_text=s.event,
                   sequence=f'{s.token}:{s.sequence}',port=detector_port,conf=float(conf),
                   relay=s.relay,video_events=s.video_events,video_id=f'{s.token}:{s.video_id}',key='thai_speech',default=None)
    # Relay path: the browser could not reach the detector port (e.g. Streamlit Cloud).
    if (isinstance(message,dict) and message.get('reset_id')==session_key and isinstance(message.get('seq'),int)
            and isinstance(message.get('jpeg'),str) and message['seq']!=s.relay_seq and len(message['jpeg'])<2000000):
        s.relay_seq=message['seq']
        try:
            frame=cv2.imdecode(np.frombuffer(base64.b64decode(message['jpeg'],validate=True),dtype=np.uint8),cv2.IMREAD_COLOR)
            result=build_response(frame,detect_frame,float(conf)) if frame is not None else {'boxes':[],'text':'','fps':0,'quality':'อ่านภาพกล้องไม่ได้'}
        except Exception as exc:
            result={'boxes':[],'text':'','fps':0,'quality':f'ประมวลผลไม่ได้: {exc}'}
        s.relay={'seq':message['seq'],**result}
        st.rerun(scope='fragment')
    status_slot.write(s.status)
    if s.quality:warn_slot.warning(s.quality)
    else:warn_slot.empty()
    if s.image is not None:image_slot.image(s.image,channels='RGB',width='stretch')
    else:image_slot.empty()
    if s.last_frame>=0 or s.image is not None:fps_slot.caption(f'ความเร็วโมเดลล่าสุด {s.fps:.1f} ภาพ/วินาที ')
    else:fps_slot.empty()
    if s.rows:
        from collections import Counter
        counts=Counter(row['ชนิด (บาท)'] for row in s.rows)
        table_slot.dataframe([{'ชนิด (บาท)':value,'จำนวน (ใบ)':count} for value,count in sorted(counts.items())],hide_index=True,width='stretch')
    else:table_slot.empty()
    if s.current:ok_slot.success(s.current)
    else:ok_slot.empty()

if s.video is not None:st.video(s.video,format='video/mp4')
live_panel()
st.caption('กรอบเทา: ตรวจพบแล้ว • กรอบเขียว: ยืนยันต่อเนื่อง • พูดทันทีที่ตรวจพบ ไม่ต้องกดปุ่ม | กล้องผ่านเบราว์เซอร์ ใช้ localhost หรือ HTTPS')
