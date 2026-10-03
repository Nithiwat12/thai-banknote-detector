// Keep one active utterance and only the latest pending result. Never interrupt
// speech on a transient missed frame. Stop/mute explicitly cancel everything.
const synth=window.speechSynthesis;
const statusNode=document.getElementById('status');
const voicesNode=document.getElementById('voices');
let enabled=true,lastSeq=null,current='',lastRender=Date.now(),generation=0;
let resetId=null,active=null,pending='',lastSpoken='';
function send(type,extra={}){window.parent.postMessage({isStreamlitMessage:true,type,...extra},'*');}
function voices(){
  if(!synth)return;
  const old=voicesNode.value;
  voicesNode.replaceChildren();
  synth.getVoices().filter(v=>v.lang.toLowerCase().replace('_','-').startsWith('th')).forEach(v=>{
    const option=document.createElement('option');option.value=v.voiceURI;option.textContent=v.name;voicesNode.append(option);
  });
  let saved='';try{saved=localStorage.getItem('thaiVoice')||'';}catch(e){}
  if([...voicesNode.options].some(v=>v.value===old))voicesNode.value=old;
  else if([...voicesNode.options].some(v=>v.value===saved))voicesNode.value=saved;
  if(!voicesNode.options.length){
    statusNode.textContent='กำลังรอเสียงภาษาไทย หากไม่ปรากฏให้ติดตั้งเสียงไทยแล้วเปิดเบราว์เซอร์ใหม่';
  }else if(!active){
    statusNode.textContent=enabled?'พร้อมพูดเมื่อพบธนบัตร':'ปิดเสียงประกาศอยู่';
    if(enabled&&pending)flush();
  }
}
function cancel(){generation++;pending='';active=null;lastSpoken='';if(synth)synth.cancel();}
function flush(){
  if(!enabled||!pending||active||!synth)return;
  const voice=synth.getVoices().find(v=>v.voiceURI===voicesNode.value);
  if(!voice){statusNode.textContent='กำลังรอเสียงภาษาไทย';return;}
  const text=pending;pending='';
  const token=generation;
  const u=new SpeechSynthesisUtterance(text);active=u;lastSpoken=text;
  u.lang='th-TH';u.voice=voice;u.rate=1.05;u.volume=1;
  u.onstart=()=>{if(token===generation)statusNode.textContent='กำลังอ่าน: '+text;};
  u.onend=()=>{
    if(token!==generation)return;
    active=null;statusNode.textContent='พร้อมพูดเมื่อพบธนบัตร';flush();
  };
  u.onerror=e=>{
    if(token!==generation)return;
    active=null;lastSpoken='';
    statusNode.textContent='เล่นเสียงไม่ได้: '+e.error+' — ลองติ๊กเปิดกล้องใหม่ และตรวจระดับเสียง/การปิดเสียงแท็บ';
  };
  try{synth.resume();synth.speak(u);}catch(e){active=null;statusNode.textContent='เล่นเสียงไม่ได้: '+e.message;}
}
function speak(text,force=false){
  if(!enabled||!text)return;
  if(force){cancel();}
  if(active&&active.text===text){pending='';return;}
  pending=text;flush();
}
const soundBox=document.getElementById('sound-toggle');
soundBox.onchange=()=>{
  enabled=soundBox.checked;
  if(!enabled){cancel();statusNode.textContent='ปิดเสียงประกาศแล้ว';}
  else{voices();speak(current||'เปิดเสียงประกาศแล้ว',true);}
};
voicesNode.onchange=()=>{try{localStorage.setItem('thaiVoice',voicesNode.value);}catch(e){}if(enabled)speak(current||'พร้อมตรวจจับธนบัตร',true);};
// Called from the camera checkbox click (a user gesture inside this frame).
function toggleOn(){return document.getElementById('camera-toggle').checked;}
window.bankSpeech={
  say(text){current=text;speak(text);},
  unlock(text){enabled=soundBox.checked;if(enabled){voices();speak(text,true);}},
  stop(){cancel();statusNode.textContent='ปิดกล้องแล้ว';}
};
// ---- Uploaded video: speak the detections while the video plays, in sync with its timeline ----
let videoEvents=[],videoId=null,boundVideo=null,lastEventIdx=-1;const boundSet=new WeakSet();
function eventIndexAt(time){let i=-1;for(let k=0;k<videoEvents.length;k++){if(videoEvents[k].t<=time)i=k;else break;}return i;}
function findVideo(){
  try{const list=window.parent.document.querySelectorAll('video');return list.length?list[list.length-1]:null;}catch(e){return null;}
}
function syncVideo(){
  const v=findVideo();
  if(v!==boundVideo){
    boundVideo=v;lastEventIdx=v?eventIndexAt(v.currentTime):-1;
    if(v&&!boundSet.has(v)){boundSet.add(v);
      v.addEventListener('pause',()=>cancel());
      v.addEventListener('seeked',()=>{lastEventIdx=eventIndexAt(v.currentTime);if(!v.paused&&lastEventIdx>=0)speak(videoEvents[lastEventIdx].text,true);});
      v.addEventListener('play',()=>{if(v.currentTime<.05)lastEventIdx=-1;});
    }
  }
  if(!v||v.paused||v.ended||!videoEvents.length||toggleOn())return;
  const idx=eventIndexAt(v.currentTime);
  if(idx>lastEventIdx){lastEventIdx=idx;speak(videoEvents[idx].text);}   // newest passed event only
  else if(idx<lastEventIdx)lastEventIdx=idx;                              // video looped / rewound
}
setInterval(syncVideo,100);
window.addEventListener('message',e=>{
  if(e.source!==window.parent||e.data?.type!=='streamlit:render')return;
  const a=e.data.args||{};lastRender=Date.now();
  if(Array.isArray(a.video_events)){videoEvents=a.video_events;if(videoId!==a.video_id){videoId=a.video_id;lastEventIdx=-1;boundVideo=null;cancel();}}
  if(resetId!==a.reset_id){resetId=a.reset_id;cancel();lastSeq=null;}
  current=a.current_text||'';
  if(!current&&!toggleOn())pending='';
  if(a.sequence!==lastSeq){lastSeq=a.sequence;if(a.event_text&&a.event_text===current)speak(a.event_text);}
  send('streamlit:setFrameHeight',{height:Math.ceil(document.body.scrollHeight+16)});
});
setInterval(()=>{if(!toggleOn()&&Date.now()-lastRender>10000){cancel();current='';}},2000);
window.addEventListener('pagehide',cancel);
if(synth){synth.addEventListener('voiceschanged',voices);voices();}
else statusNode.textContent='เบราว์เซอร์นี้ไม่รองรับเสียงพูด ลอง Chrome หรือ Edge';
send('streamlit:componentReady',{apiVersion:1});
send('streamlit:setFrameHeight',{height:Math.ceil(document.body.scrollHeight+16)});
