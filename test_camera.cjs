const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const events={},messages=[],timers=[];let now=1000,stops=0,opens=0;
const ctx={clearRect(){},drawImage(){},strokeRect(){},fillText(){}};
const video={videoWidth:640,videoHeight:480,readyState:2,srcObject:null,play:async()=>{}};
const nodes={'camera-video':video,'camera-panel':{},'camera-status':{},'camera-overlay':{width:640,height:480,getContext:()=>ctx},'camera-retry':{}};
const stream={getTracks:()=>[{stop(){stops++;}}]};
const parent={postMessage:m=>messages.push(m)};
const context={window:{parent,addEventListener:(n,f)=>events[n]=f},document:{body:{scrollHeight:640},getElementById:id=>nodes[id],createElement:()=>({getContext:()=>ctx,toDataURL:()=> 'data:image/jpeg;base64,AAAA'})},navigator:{mediaDevices:{getUserMedia:async()=>{opens++;return stream;}}},Date,performance:{now:()=>now},setInterval:f=>timers.push(f)};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/speech_component/camera.js','utf8'),context);
function render(reset_id,camera_active,ack_seq=-1){events.message({source:parent,data:{type:'streamlit:render',args:{reset_id,camera_active,ack_seq,boxes:[]}}});}
(async()=>{
 render('a',true);await new Promise(r=>setImmediate(r));
 assert.equal(video.srcObject,stream);assert.equal(opens,1);
 timers[0]();const frames=()=>messages.filter(m=>m.type==='streamlit:setComponentValue');
 assert.equal(frames().length,1);
 for(let i=0;i<100;i++){now+=50;timers[0]();}
 assert.equal(frames().length,1);assert.equal(video.srcObject,stream); // no queued frames, preview stays live
 render('a',true,1);now+=100;timers[0]();assert.equal(frames().length,2);
 assert.equal(frames()[1].value.seq,2);
 render('b',false);assert.equal(video.srcObject,null);assert.equal(stops,1);
 render('c',true);await new Promise(r=>setImmediate(r));assert.equal(opens,2);
 events.pagehide();assert.equal(stops,2);
 console.log('Camera: native preview, single frame in flight, ack, reset, reopen and release passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
