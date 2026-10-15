import { afterEach, beforeEach, expect, it, vi } from "vitest";
const api=vi.hoisted(() => ({prepareVoice:vi.fn(),discardVoicePreparation:vi.fn(),voicePreparation:vi.fn(),voicePreparationDelivered:vi.fn()}));
vi.mock("./localApi",() => ({localApi:api}));
import { VoiceLivePreparation } from "./voiceLivePreparation";

const delta=(text:string,item="asr") => ({type:"conversation.item.input_audio_transcription.delta",item_id:item,content_index:0,delta:text});
const ready=(memories:{id:string;text:string}[]=[]) => ({revision:1,state:"ready",memories:memories.map(m => ({...m,methods:[]})),tools:[]});

beforeEach(() => {
  vi.clearAllMocks();
  api.voicePreparation.mockResolvedValue(ready());
  api.prepareVoice.mockResolvedValue({});
  api.discardVoicePreparation.mockResolvedValue({});
  api.voicePreparationDelivered.mockResolvedValue({});
});
afterEach(() => { vi.useRealTimers(); });

it("searches on partial speech while the user is still talking and never gates the response",async () => {
  const send=vi.fn();
  const live=new VoiceLivePreparation("voice",send);
  live.sessionUpdate({type:"session.update",session:{instructions:"Base"}});
  api.voicePreparation.mockResolvedValue(ready([{id:"m1",text:"Relevant fact"}]));
  live.speechStarted("item");
  live.transcript(delta("Find my"));
  live.transcript(delta(" contacts please"));
  await vi.waitFor(() => expect(api.prepareVoice).toHaveBeenCalledWith("voice",
    expect.objectContaining({text:"Find my contacts please",revision:2})));
  await vi.waitFor(() => expect(send.mock.calls.some(([e]) => String(e.session?.instructions).includes("Relevant fact"))).toBe(true));
  const updates=send.mock.calls.map(([e]) => e);
  expect(updates.every(e => e.type==="session.update" && e.session.type==="realtime")).toBe(true);
  expect(updates.some(e => e.type==="response.create")).toBe(false);
  live.close();
});

it("keeps retrieved memory in the instructions after the indicator hides, until the next utterance",async () => {
  vi.useFakeTimers({shouldAdvanceTime:true});
  const send=vi.fn(),display=vi.fn();
  const live=new VoiceLivePreparation("voice",send,display);
  live.sessionUpdate({type:"session.update",session:{instructions:"Base"}});
  api.voicePreparation.mockResolvedValue(ready([{id:"m1",text:"Relevant fact"}]));
  live.speechStarted("item");
  live.transcript(delta("Find my contacts please"));
  await vi.waitFor(() => expect(display).toHaveBeenCalledWith(expect.objectContaining({state:"ready"})));
  send.mockClear();display.mockClear();
  await vi.advanceTimersByTimeAsync(4100);
  expect(display).toHaveBeenCalledWith(null);
  expect(send).not.toHaveBeenCalled(); // memory still applies to the in-flight answer and tool follow-ups
  live.speechStarted("next");
  expect(send.mock.calls.at(-1)?.[0]).toEqual({type:"session.update",session:{type:"realtime",instructions:"Base"}});
  live.close();
});

it("Live Memory Off stops the transcription session without touching the response",async () => {
  api.prepareVoice.mockResolvedValue({enabled:false});
  const send=vi.fn(),live=new VoiceLivePreparation("voice",send);
  const stop=vi.spyOn(live,"stopTranscription");
  live.speechStarted("item");
  await vi.waitFor(() => expect(stop).toHaveBeenCalled());
  expect(send.mock.calls.some(([e]) => e.type==="response.create")).toBe(false);
  live.close();
});

it("rejects a late result from a prior utterance and publishes the current one", async () => {
  const display=vi.fn(),live=new VoiceLivePreparation("voice",vi.fn(),display,true);
  let resolve!:(v:unknown)=>void;
  api.voicePreparation.mockImplementationOnce(() => new Promise(r => {resolve=r;}));
  live.speechStarted("old");live.completedTranscript("old","Find my contacts");
  await vi.waitFor(() => expect(api.voicePreparation).toHaveBeenCalled());
  live.speechStarted("new");display.mockClear();
  resolve(ready([{id:"old",text:"old"}]));
  await Promise.resolve();expect(display).not.toHaveBeenCalled();
  live.completedTranscript("new","Search the web now");
  await vi.waitFor(() => expect(display).toHaveBeenCalledWith(expect.objectContaining({state:"ready"})));
  live.close();
});

it("OAuth conversation transcripts update instructions without creating a response and preserve mode updates", async () => {
  const send=vi.fn(),live=new VoiceLivePreparation("voice",send,vi.fn(),true);
  live.sessionUpdate({type:"session.update",session:{instructions:"Original mode"}});
  api.voicePreparation.mockResolvedValue({revision:1,state:"searching",memories:[{id:"memory",text:"Relevant fact",methods:[]}],tools:[]});
  live.speechStarted("item");
  live.completedTranscript("item","Find my contacts");
  await vi.waitFor(() => expect(send).toHaveBeenCalled());
  expect(send.mock.calls[0][0]).toMatchObject({type:"session.update",session:{instructions:expect.stringContaining("Original mode")}});
  expect(send.mock.calls[0][0].session.instructions).toContain("Relevant fact");
  const updated=live.sessionUpdate({type:"session.update",session:{instructions:"New mode",tools:[]}});
  expect((updated.session as any).instructions).toContain("New mode");
  expect((updated.session as any).instructions).toContain("Relevant fact");
  expect(send.mock.calls.every(([e]) => e.type==="session.update")).toBe(true);
  live.speechStarted("next");
  expect(send.mock.calls.at(-1)?.[0]).toEqual({type:"session.update",session:{type:"realtime",instructions:"New mode"}});
  live.close();
});

it("ignores transcript deltas for another conversation item on the OAuth connection", async () => {
  const live=new VoiceLivePreparation("voice",vi.fn(),vi.fn(),true);
  live.speechStarted("item");
  live.conversationDelta(delta("Find my contacts please","other"));
  await new Promise(resolve => setTimeout(resolve, 30));
  // Only the speech-start reset reached the server; the foreign item's text was never posted.
  expect(api.prepareVoice).toHaveBeenCalledTimes(1);
  expect(api.prepareVoice).toHaveBeenCalledWith("voice",expect.objectContaining({text:""}));
  live.close();
});

it("with a dedicated transcription session, conversation-connection deltas never mix into the search text", async () => {
  // OAuth conversation + API-key transcription session: the sidecar is the only text source.
  const live=new VoiceLivePreparation("voice",vi.fn(),vi.fn());
  live.speechStarted("item");
  live.transcript(delta("Find my contacts","sidecar"));
  live.conversationDelta(delta("late post-commit text","item"));
  await vi.waitFor(() => expect(api.prepareVoice).toHaveBeenCalledWith("voice",
    expect.objectContaining({text:"Find my contacts",revision:1})));
  await new Promise(resolve => setTimeout(resolve, 30));
  const texts=api.prepareVoice.mock.calls.map(([,body]) => body.text);
  expect(texts).not.toContain("late post-commit text");
  expect(texts.every(text => text==="" || "Find my contacts".startsWith(text))).toBe(true);
  live.close();
});

it("keeps memory and the panel while speech continues, and ignores superseded 'stale' answers", async () => {
  const send=vi.fn(),display=vi.fn();
  const live=new VoiceLivePreparation("voice",send,display);
  live.sessionUpdate({type:"session.update",session:{instructions:"Base"}});
  api.voicePreparation.mockResolvedValueOnce({revision:1,state:"searching",memories:[{id:"m1",text:"Fact one",methods:[]}],tools:[]});
  live.speechStarted("item");
  live.transcript(delta("Find my contacts"));
  await vi.waitFor(() => expect(display).toHaveBeenCalledWith(expect.objectContaining({state:"searching"})));
  send.mockClear(); display.mockClear();
  api.voicePreparation.mockResolvedValue({revision:2,state:"stale",memories:[],tools:[]});
  live.transcript(delta(" for Sarah please"));
  await vi.waitFor(() => expect(api.voicePreparation).toHaveBeenCalledWith("voice",expect.any(String),2));
  await new Promise(resolve => setTimeout(resolve, 30));
  expect(display).not.toHaveBeenCalled();  // no clear between words
  expect(send).not.toHaveBeenCalled();     // memory context stays in the instructions
  live.close();
});

it("reports a count-only delivery receipt when live memory reaches the agent", async () => {
  const live=new VoiceLivePreparation("voice",vi.fn(),vi.fn());
  api.voicePreparation.mockResolvedValue(ready([{id:"m1",text:"Fact one"},{id:"m2",text:"Fact two"}]));
  live.speechStarted("item");
  live.transcript(delta("Find my contacts please"));
  await vi.waitFor(() => expect(api.voicePreparationDelivered).toHaveBeenCalledWith("voice",expect.any(String),2,0));
  expect(api.voicePreparationDelivered).toHaveBeenCalledTimes(1);
  live.close();
});

it("hands the live tool route to the agent as a hint and reports it", async () => {
  const send=vi.fn(),live=new VoiceLivePreparation("voice",send,vi.fn());
  live.sessionUpdate({type:"session.update",session:{instructions:"Base"}});
  api.voicePreparation.mockResolvedValue({revision:1,state:"ready",memories:[],
    tools:[{id:"builtin.contacts-search.v1",name:"contacts_search",description:"Propose contacts_search",kind:"catalog_proposal"}]});
  live.speechStarted("item");
  live.transcript(delta("Find Sarah in my contacts"));
  await vi.waitFor(() => expect(send.mock.calls.some(([e]) => String(e.session?.instructions).includes("Live tool route"))).toBe(true));
  const update=send.mock.calls.map(([e]) => e).find(e => String(e.session?.instructions).includes("Live tool route"));
  expect(update.session.instructions).toContain("contacts_search");
  expect(send.mock.calls.some(([e]) => e.type==="response.create")).toBe(false);
  await vi.waitFor(() => expect(api.voicePreparationDelivered).toHaveBeenCalledWith("voice",expect.any(String),0,1));
  live.close();
});

it("shows results during continuous speech even when each word arrives before Vault answers the last", async () => {
  const display=vi.fn(),live=new VoiceLivePreparation("voice",vi.fn(),display);
  const pending:Array<() => void>=[];
  api.prepareVoice.mockImplementation(() => new Promise(resolve => pending.push(() => resolve({}))));
  api.voicePreparation.mockImplementation((_s,_u,revision) => Promise.resolve({...ready([{id:"m1",text:"Link platform"}]),revision}));
  live.speechStarted("item");
  await vi.waitFor(() => expect(pending.length).toBe(1)); pending.shift()!();  // speech-start reset
  live.transcript(delta("So the Link"));
  for (const word of [" platform"," I"," wanted"," to"," talk"]) {
    await vi.waitFor(() => expect(pending.length).toBe(1));
    live.transcript(delta(word));            // the next word lands while Vault is still answering the previous one
    pending.shift()!();
  }
  // Still speaking (no speechStopped): the window already has the found memory.
  await vi.waitFor(() => expect(display).toHaveBeenCalledWith(expect.objectContaining({memories:[expect.objectContaining({text:"Link platform"})]})));
  expect(api.voicePreparation).toHaveBeenCalled();
  live.close();
});
