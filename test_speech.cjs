const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const nodes={};
for(const id of ['status','voices','enable','mute','repeat'])nodes[id]={textContent:'',value:'',options:[],replaceChildren(){this.options=[];this.value='';},append(v){this.options.push(v);if(!this.value)this.value=v.value;}};
const events={},spoken=[];let cancels=0,voiceList=[];
const synth={getVoices:()=>voiceList,cancel(){cancels++;},resume(){},speak(u){spoken.push(u);},addEventListener:(n,f)=>events[n]=f};
const parent={postMessage(){}};
const context={window:{speechSynthesis:synth,parent,addEventListener:(n,f)=>events[n]=f},document:{body:{scrollHeight:145},getElementById:id=>nodes[id],createElement:()=>({})},Date,setInterval(){},SpeechSynthesisUtterance:function(text){this.text=text;}};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/speech_component/speech.js','utf8'),context);
function render(sequence,current_text,event_text,reset_id='session:0'){events.message({source:parent,data:{type:'streamlit:render',args:{sequence,current_text,event_text,reset_id}}});}
const a='พบธนบัตร หนึ่งร้อยบาท 2 ใบ',b='พบธนบัตร ห้าร้อยบาท 1 ใบ',c='พบธนบัตร ยี่สิบบาท 3 ใบ';
render('1',a,a);assert.equal(spoken.length,0);
nodes.enable.onclick();assert.equal(spoken.length,0);
voiceList=[{voiceURI:'thai',name:'Thai voice',lang:'th-TH'}];events.voiceschanged();
assert.equal(spoken.at(-1).text,a);assert.doesNotMatch(nodes.status.textContent,/ติดตั้ง/);
let before=cancels;
render('2','','');assert.equal(cancels,before); // missed frame must not cut off speech
render('3',b,b);assert.equal(spoken.length,1); // finish active utterance first
render('4',c,c);spoken[0].onend();assert.equal(spoken.at(-1).text,c);assert.equal(spoken.length,2); // latest pending only
render('4',c,c);assert.equal(spoken.length,2);
render('5','','','session:1');assert.ok(cancels>before);
nodes.repeat.onclick();assert.equal(spoken.at(-1).text,'ยังไม่พบธนบัตร');
nodes.mute.onclick();const n=spoken.length;render('6',a,a,'session:1');assert.equal(spoken.length,n);
nodes.enable.onclick();assert.equal(spoken.at(-1).text,a); // enable after detection reads current result
console.log('Speech: async voices, current result, no frame interruption, latest pending, reset, mute, repeat passed');
