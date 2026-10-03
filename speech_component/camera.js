// Camera loop runs fully in the browser: grab frame -> POST to local detector -> draw boxes
// -> speak immediately. No Streamlit rerun in the loop.
const cameraVideo=document.getElementById('camera-video');
const cameraPanel=document.getElementById('camera-panel');
const cameraStatus=document.getElementById('camera-status');
const overlay=document.getElementById('camera-overlay');
const toggle=document.getElementById('camera-toggle');
const capture=document.createElement('canvas');
let port=null,conf=.6,cameraReset=null,cameraStream=null,cameraWanted=false,openToken=0;
let streamId='',pendingText='',pendingSince=0;
let lastText='',lastAnnounce=0,lastSeen=0,relaySeq=0,relayPending=null;
function blobToB64(blob){return new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(blob);});}
// Fallback when the local detector port is unreachable (e.g. Streamlit Cloud): send the frame
// through Streamlit itself and wait for the result to come back in the render args.
async function relayDetect(blob){
  const jpeg=await blobToB64(blob),seq=++relaySeq;
  const reply=new Promise((res,rej)=>{relayPending={seq,res};setTimeout(()=>{if(relayPending&&relayPending.seq===seq){relayPending=null;rej(new Error('หมดเวลารอผล'));}},20000);});
  cameraPost('streamlit:setComponentValue',{value:{reset_id:cameraReset,stream:streamId,seq,jpeg},dataType:'json'});
  return reply;
}
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
function cameraPost(type,extra={}){window.parent.postMessage({isStreamlitMessage:true,type,...extra},'*');}
function cameraHeight(){cameraPost('streamlit:setFrameHeight',{height:Math.ceil(document.body.scrollHeight+16)});}
function clearOverlay(){overlay.getContext('2d').clearRect(0,0,overlay.width,overlay.height);}
function stopCamera(){
  openToken++;
  if(cameraStream)cameraStream.getTracks().forEach(t=>t.stop());
  cameraStream=null;cameraVideo.srcObject=null;clearOverlay();lastText='';pendingText='';
}
function drawBoxes(list){
  overlay.width=cameraVideo.videoWidth;overlay.height=cameraVideo.videoHeight;
  const ctx=overlay.getContext('2d'),w=overlay.width,h=overlay.height;
  ctx.clearRect(0,0,w,h);ctx.strokeStyle='#39ed71';ctx.fillStyle='#39ed71';ctx.lineWidth=3;ctx.font='bold 20px sans-serif';
  for(const it of list){
    const [x1,y1,x2,y2]=it.box;
    ctx.strokeRect(x1*w,y1*h,(x2-x1)*w,(y2-y1)*h);ctx.fillText(it.label,x1*w+2,Math.max(20,y1*h-6));
  }
}
function announce(text){
  const now=performance.now();
  if(text){
    lastSeen=now;
    if(text!==pendingText){pendingText=text;pendingSince=now;}
    if(now-pendingSince<250)return;
    if(text!==lastText&&now-lastAnnounce>=1200){lastText=text;lastAnnounce=now;try{window.bankSpeech&&window.bankSpeech.say(text);}catch(e){}}
  }else{pendingText='';if(now-lastSeen>2000)lastText='';}
}
async function loop(token){
  let fails=0,relay=!port;
  if(!relay){
    try{const ctl=new AbortController();setTimeout(()=>ctl.abort(),2500);await fetch(`http://${location.hostname}:${port}/`,{signal:ctl.signal});}
    catch(e){relay=true;}
  }
  while(token===openToken&&cameraWanted){
    if(cameraVideo.readyState<2||!cameraVideo.videoWidth){await sleep(100);continue;}
    const scale=Math.min(1,640/cameraVideo.videoWidth);
    capture.width=Math.round(cameraVideo.videoWidth*scale);capture.height=Math.round(cameraVideo.videoHeight*scale);
    capture.getContext('2d').drawImage(cameraVideo,0,0,capture.width,capture.height);
    const blob=await new Promise(r=>capture.toBlob(r,'image/jpeg',.8));
    const staleTimer=setTimeout(()=>{if(token===openToken)clearOverlay();},700);
    try{
      let j;
      if(relay)j=await relayDetect(blob);
      else{const ctl=new AbortController();const timer=setTimeout(()=>ctl.abort(),8000);try{const res=await fetch(`http://${location.hostname}:${port}/detect?conf=${conf}&stream=${encodeURIComponent(streamId)}`,{method:'POST',body:blob,signal:ctl.signal});j=await res.json();}finally{clearTimeout(timer);}}
      if(token!==openToken)return;
      if(j.error)throw new Error(j.error);
      fails=0;drawBoxes(j.boxes);announce(j.text);
      cameraStatus.textContent=(j.quality||(j.text?('ตรวจพบ: '+j.text):'กล้องสด • กำลังตรวจจับ ยังไม่พบธนบัตร'))+` • ${j.fps} ภาพ/วินาที`;
    }catch(e){
      if(token!==openToken)return;
      clearOverlay();pendingText='';fails++;cameraStatus.textContent='เชื่อมต่อตัวตรวจจับไม่ได้ ('+e.message+') กำลังลองใหม่...';
      await sleep(Math.min(3000,500*fails));
    }finally{clearTimeout(staleTimer);}
  }
}
async function openCamera(){
  if(!cameraWanted||cameraStream)return;
  const token=++openToken;
  cameraStatus.textContent='กรุณาอนุญาตกล้องในเบราว์เซอร์';
  try{
    if(!navigator.mediaDevices?.getUserMedia)throw new Error('ต้องเปิดผ่าน http://localhost:8501 หรือ HTTPS');
    const stream=await navigator.mediaDevices.getUserMedia({audio:false,video:{width:{ideal:640},height:{ideal:480},frameRate:{ideal:30,max:30},facingMode:'environment'}});
    if(token!==openToken||!cameraWanted){stream.getTracks().forEach(t=>t.stop());return;}
    streamId=(globalThis.crypto?.randomUUID?.()||`${Date.now()}-${Math.random()}`);
    cameraStream=stream;cameraVideo.srcObject=stream;await cameraVideo.play();
    cameraStatus.textContent='กล้องสด • กำลังตรวจจับ...';cameraHeight();
    loop(token);
  }catch(e){
    if(token!==openToken)return;
    stopCamera();toggle.checked=false;cameraWanted=false;cameraPanel.hidden=true;
    document.getElementById('status').textContent='เปิดกล้องไม่ได้: '+e.message+' — อนุญาตกล้องและปิดแอปอื่นที่ใช้กล้อง';
  }
}
toggle.onchange=()=>{
  cameraWanted=toggle.checked;cameraPanel.hidden=!cameraWanted;
  if(cameraWanted){try{window.bankSpeech&&window.bankSpeech.unlock('เปิดกล้องแล้ว');}catch(e){}
    openCamera();}
  else{stopCamera();window.bankSpeech&&window.bankSpeech.stop();}
  cameraHeight();
};
cameraVideo.onloadedmetadata=cameraHeight;
window.addEventListener('message',e=>{
  if(e.source!==window.parent||e.data?.type!=='streamlit:render')return;
  const a=e.data.args||{};
  port=a.port||null;
  if(a.relay&&relayPending&&a.relay.seq===relayPending.seq){const p=relayPending;relayPending=null;p.res(a.relay);}
  if(typeof a.conf==='number')conf=a.conf;
  if(cameraReset!==a.reset_id){
    // Server-side reset (file upload started): switch the camera off.
    stopCamera();cameraReset=a.reset_id;toggle.checked=false;cameraWanted=false;cameraPanel.hidden=true;
  }
});
window.addEventListener('pagehide',stopCamera);
window.addEventListener('resize',cameraHeight);
