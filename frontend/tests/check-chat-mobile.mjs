// Zero-dependency real Chrome layout proof, synthetic fixture only.
import { spawn } from 'node:child_process';
import { mkdtemp, readFile, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
const output = resolve(process.argv[2] ?? '/tmp/vault-chat-mobile-check');
await mkdir(output, { recursive: true });
const profile = await mkdtemp(join(tmpdir(), 'vault-chat-mobile-'));
const chrome = spawn('/usr/bin/google-chrome', ['--headless=new','--no-sandbox','--disable-gpu',
  '--no-first-run','--no-default-browser-check','--remote-debugging-port=0',`--user-data-dir=${profile}`,'about:blank'], { stdio:'ignore' });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
try {
  let port;
  for (let i=0;i<100;i++) {
    try { port = (await readFile(join(profile,'DevToolsActivePort'),'utf8')).split('\n')[0]; break; } catch { await pause(50); }
  }
  if (!port) throw Error('Chrome debugger did not start');
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`,{method:'PUT'})).json();
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => { socket.onopen=resolve; socket.onerror=reject; });
  let next=0;
  const pending = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (!message.id) return;
    const request = pending.get(message.id); pending.delete(message.id);
    message.error ? request.reject(Error(JSON.stringify(message.error))) : request.resolve(message.result);
  };
  function send(method,params={}) {
    const id=++next;
    return new Promise((resolve,reject) => { pending.set(id,{resolve,reject}); socket.send(JSON.stringify({id,method,params})); });
  }
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await send('Page.enable');
  const results=[];
  for (const [width,height] of [[360,800],[390,844],[768,1024],[667,375]]) {
    await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:true});
    await send('Page.navigate',{url:'http://127.0.0.1:4176/tests/chat-mobile.html'});
    let ready=false;
    for(let i=0;i<150;i++) {
      ready = await evaluate(`document.documentElement?.dataset.mobileReady === 'true' && document.querySelectorAll('.vault-chat-message').length >= 20`);
      if(ready)break;
      await pause(100);
    }
    if(!ready)throw Error('Actual Chat fixture failed to load');
    await pause(200);
    await evaluate(`document.querySelector('.vault-chat-jump')?.click()`);
    if (process.argv.includes('--preparation')) {
      await evaluate(`(() => { const input=document.querySelector('.vault-chat-composer textarea');
        Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(input,'Find the project memory');
        input.dispatchEvent(new Event('input',{bubbles:true})); })()`);
      let visible=false;
      for(let i=0;i<50;i++) {
        visible=await evaluate(`!!document.querySelector('.vault-chat-preparation li')`);
        if(visible)break;
        await pause(100);
      }
      if(!visible)throw Error('Actual live observer did not render the synthetic backend envelope');
    }
    await pause(200);
    const metrics = await evaluate(`(() => {
      const rect = selector => { const r=document.querySelector(selector).getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right}; };
      const viewport=document.querySelector('.vault-chat-scroll');
      return { width:innerWidth,height:innerHeight,chat:rect('.vault-chat'),composer:rect('.vault-chat-composer'),
        mic:rect('.vault-chat-microphone'),send:rect('.vault-chat-composer button[type="submit"]'),
        micHidden:getComputedStyle(document.querySelector('.vault-chat-microphone')).display==='none',
        nav:rect('.browser-voice-future-nav.is-mobile'),scroll:rect('.vault-chat-scroll'),
        horizontalOverflow:viewport.scrollWidth>viewport.clientWidth+1,
        messageScroll:viewport.scrollHeight>viewport.clientHeight,
        textareaFont:getComputedStyle(document.querySelector('.vault-chat-composer textarea')).fontSize};
    })()`);
    results.push({viewport:[width,height],...metrics});
    if(metrics.horizontalOverflow || metrics.composer.bottom>metrics.nav.y || metrics.send.bottom>metrics.height
        || !metrics.micHidden || metrics.mic.width!==0 || metrics.send.height<44 || metrics.scroll.height<32 || !metrics.messageScroll)
      throw Error(`Mobile layout regression at ${width}x${height}: ${JSON.stringify(metrics)}`);
    const image = await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
    await writeFile(join(output,`${width}x${height}.png`),Buffer.from(image.data,'base64'));
  }
  await writeFile(join(output,'metrics.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify({output,results},null,2));
} finally {
  socket?.close(); chrome.kill('SIGTERM');
}
