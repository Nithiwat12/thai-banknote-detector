const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let now=0;const spoken=[];const ctx={clearRect(){}};const node={getContext:()=>ctx};
const context={window:{parent:{postMessage(){}},addEventListener(){},bankSpeech:{say:t=>spoken.push(t)}},document:{getElementById:()=>node,createElement:()=>({})},performance:{now:()=>now},setTimeout,clearTimeout};
vm.createContext(context);vm.runInContext(fs.readFileSync(__dirname+'/speech_component/camera.js','utf8'),context);
context.announce('50 x 1');assert.deepEqual(spoken,['50 x 1']);
now=10;context.announce('50 x 1');assert.equal(spoken.length,1);
now=20;context.announce('100 x 1');assert.equal(spoken.length,2);
console.log('Immediate speech and dedup passed');
