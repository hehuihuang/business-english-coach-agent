import { FormEvent, useEffect, useRef, useState } from "react";
import {
  Activity, ArrowUp, AudioLines, BookOpen, Check, ChevronRight, ClipboardCheck,
  Database, FileText, Gauge, Library, LogOut, Mic, Pause, Play, Plus, Search,
  Settings2, Sparkles, Square, Upload, UserRound, WandSparkles,
} from "lucide-react";
import { api, CoachResponse } from "./api";

type Page = "today" | "studio" | "notebook" | "knowledge" | "evaluation" | "observatory";

const nav: Array<{ id: Page; label: string; kicker: string; icon: typeof BookOpen }> = [
  { id: "today", label: "Today", kicker: "今日学习", icon: Sparkles },
  { id: "studio", label: "Practice Studio", kicker: "训练室", icon: AudioLines },
  { id: "notebook", label: "Review Notebook", kicker: "记忆簿", icon: BookOpen },
  { id: "knowledge", label: "Knowledge Library", kicker: "知识库", icon: Library },
  { id: "evaluation", label: "Evaluation Lab", kicker: "评测实验室", icon: ClipboardCheck },
  { id: "observatory", label: "Run Observatory", kicker: "运行观测台", icon: Activity },
];

function Login({ onReady }: { onReady: () => void }) {
  const [email, setEmail] = useState("learner@example.com");
  const [password, setPassword] = useState("learn-english");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { await api.login(email, password); onReady(); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function demo() {
    setBusy(true); setError("");
    try { await api.bootstrapDemo(); onReady(); }
    catch (err) { setError(`请先启动后端：${(err as Error).message}`); }
    finally { setBusy(false); }
  }

  return <main className="login-page">
    <div className="edition-mark">ISSUE 01 · THE WORKING ENGLISH EDITION</div>
    <section className="login-copy">
      <div className="red-rule" />
      <p className="eyebrow">A COACH THAT SHOWS ITS WORK</p>
      <h1>Your English,<br /><em>in the margins.</em></h1>
      <p className="dek">练表达，也看懂一个生产级 Agent 如何规划、检索、调用工具、记忆、评测与自我改进。</p>
      <div className="proof-strip">
        <span><b>6</b> graph nodes</span><span><b>4</b> memory types</span><span><b>100%</b> traceable</span>
      </div>
    </section>
    <form className="login-card" onSubmit={submit}>
      <div className="card-number">MEMBER DESK / 会员入口</div>
      <h2>Open your notebook</h2>
      <label>Email<input value={email} onChange={(e) => setEmail(e.target.value)} type="email" /></label>
      <label>Password<input value={password} onChange={(e) => setPassword(e.target.value)} type="password" /></label>
      {error && <p className="error-note">{error}</p>}
      <button className="ink-button" disabled={busy}>{busy ? "Opening…" : "Enter the studio"}<ArrowUp size={17} /></button>
      <button type="button" className="text-button" onClick={demo}>创建并进入本地演示账号</button>
      <p className="fineprint">演示模式默认使用 Mock 模型，不会把内容发送给外部服务。</p>
    </form>
  </main>;
}

function Sidebar({ page, setPage, user, logout }: any) {
  return <aside className="sidebar">
    <div className="brand"><span className="brand-glyph">M<span>✎</span></span><div><b>Margin Notes</b><small>BUSINESS ENGLISH COACH</small></div></div>
    <nav>{nav.map((item, index) => {
      const Icon = item.icon;
      return <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => setPage(item.id)}>
        <span className="nav-index">0{index + 1}</span><Icon size={18} /><span><b>{item.label}</b><small>{item.kicker}</small></span>
      </button>;
    })}</nav>
    <div className="sidebar-foot">
      <div className="avatar">{user?.display_name?.slice(0, 1) || "L"}</div>
      <div><b>{user?.display_name}</b><small>{user?.profile?.cefr_level} · {user?.profile?.industry}</small></div>
      <button onClick={logout} aria-label="Log out"><LogOut size={17} /></button>
    </div>
  </aside>;
}

function Today({ setPage, dashboard, user }: any) {
  return <div className="page today-page">
    <header className="page-header"><div><p className="issue">SATURDAY EDITION · PERSONAL BRIEFING</p><h1>Good morning, {user?.display_name?.split(" ")[0]}.</h1><p>今天，把“礼貌”写得更明确一点。</p></div><div className="date-stamp"><b>05</b><span>SEP<br />2026</span></div></header>
    <section className="lead-grid">
      <article className="feature-card">
        <span className="section-tag">TODAY'S ASSIGNMENT</span>
        <h2>Disagree without<br />losing the room.</h2>
        <p>练习在会议中表达不同意见：先对齐共同目标，再指出具体风险，最后提出可执行替代方案。</p>
        <button className="red-button" onClick={() => setPage("studio")}>Start 8-minute practice <ChevronRight size={18} /></button>
        <div className="feature-note"><em>Coach’s note</em><span>“Soft” does not have to mean vague.</span></div>
      </article>
      <aside className="score-card"><div className="score-ring"><span>{user?.profile?.cefr_level || "B1"}</span><small>CURRENT LEVEL</small></div><h3>Working profile</h3><dl><div><dt>Clarity</dt><dd><i style={{width:"72%"}} /></dd></div><div><dt>Tone</dt><dd><i style={{width:"61%"}} /></dd></div><div><dt>Specificity</dt><dd><i style={{width:"54%"}} /></dd></div></dl><button onClick={() => setPage("notebook")}>Read the full notes →</button></aside>
    </section>
    <section className="metrics-row">
      <div><span>RUNS</span><b>{dashboard?.runs || 0}</b><small>coaching sessions</small></div>
      <div><span>MEMORIES</span><b>{dashboard?.memories || 0}</b><small>learning signals</small></div>
      <div><span>AVG. LATENCY</span><b>{dashboard?.average_latency_ms || 0}<sup>ms</sup></b><small>end-to-end</small></div>
      <div><span>FAILURE RATE</span><b>{Math.round((dashboard?.failure_rate || 0) * 100)}<sup>%</sup></b><small>visible, not hidden</small></div>
    </section>
    <section className="column-copy"><div><span className="drop-cap">A</span><p> good business sentence carries a job: clarify, request, challenge, decide. The coach preserves that job before polishing grammar.</p></div><blockquote>“Could we pilot this with ten customers first?”<cite>FIELD NOTE / CONSTRUCTIVE DISAGREEMENT</cite></blockquote></section>
  </div>;
}

function Studio({ onRun }: { onRun: (id: string) => void }) {
  const [conversationId, setConversationId] = useState("");
  const [input, setInput] = useState("I don't agree with this plan because it is too risky.");
  const [result, setResult] = useState<CoachResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null);

  async function run() {
    if (!input.trim() || busy) return;
    setBusy(true); setError(""); setResult(null);
    try {
      let id = conversationId;
      if (!id) { id = (await api.createConversation("coach")).id; setConversationId(id); }
      const response = await api.sendMessage(id, input);
      setResult(response); onRun(response.run_id);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function toggleRecording() {
    if (recording) { recorder.current?.stop(); setRecording(false); return; }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const chunks: Blob[] = [];
    const media = new MediaRecorder(stream);
    media.ondataavailable = (event) => chunks.push(event.data);
    media.onstop = async () => {
      stream.getTracks().forEach((track) => track.stop());
      const transcription = await api.transcribe(new Blob(chunks, { type: media.mimeType }));
      setInput(transcription.text);
    };
    recorder.current = media; media.start(); setRecording(true);
  }

  async function speak() {
    if (!result) return;
    const blob = await api.speak(result.content);
    new Audio(URL.createObjectURL(blob)).play();
  }

  return <div className="page studio-page">
    <header className="page-header compact"><div><p className="issue">PRACTICE STUDIO / 实战训练室</p><h1>Write it. Say it. <em>Mean it.</em></h1></div><span className="live-mark"><i />TRACE ON</span></header>
    <div className="studio-grid">
      <section className="draft-sheet">
        <div className="sheet-head"><span>DRAFT / YOUR TURN</span><span>SCENE 01 · MEETING</span></div>
        <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Write the sentence you would really say at work…" />
        <div className="draft-tools">
          <button className={recording ? "recording" : ""} onClick={toggleRecording}>{recording ? <Square size={16} /> : <Mic size={17} />}{recording ? "Stop recording" : "Speak instead"}</button>
          <button className="send-button" onClick={run} disabled={busy}>{busy ? "Coach is working…" : "Send to coach"}<ArrowUp size={17} /></button>
        </div>
        {error && <p className="error-note">{error}</p>}
      </section>
      <aside className="assignment-rail"><span>THE BRIEF</span><h3>A director wants to launch next week. You see a support risk.</h3><p>Your goal is not to “win.” Make the concern concrete and propose a smaller first step.</p><dl><div><dt>Audience</dt><dd>Senior leader</dd></div><div><dt>Tone</dt><dd>Direct, constructive</dd></div><div><dt>Level</dt><dd>B1 → B2</dd></div></dl></aside>
    </div>
    {busy && <div className="thinking-strip"><WandSparkles size={20}/><div><b>Planning the coaching move</b><span>load context → retrieve knowledge → coach → assess → persist</span></div><i /></div>}
    {result && <section className="feedback-sheet">
      <div className="feedback-label">EDITOR'S REVISION</div>
      <div className="answer"><p>{result.content}</p><button onClick={speak} title="Listen"><Play size={17}/></button></div>
      <div className="margin-comment"><span>WHY THIS WORKS</span><p>意图没有被“润色掉”：仍然明确反对风险，但增加了共同目标和下一步。</p></div>
      <div className="score-line">{Object.entries(result.assessment).filter(([,v]) => typeof v === "number").slice(0,3).map(([key,value]) => <div key={key}><span>{key.replace("_", " ")}</span><b>{value}</b><small>/ 5</small></div>)}</div>
      <details className="trace-drawer"><summary><Activity size={16}/> See how the Agent worked <span>{result.usage.input_tokens + result.usage.output_tokens} tokens · {result.usage.latency_ms} ms</span></summary><div className="trace-content"><ol>{result.plan.map((step) => <li key={step}><Check size={14}/>{step}</li>)}</ol><pre>{JSON.stringify(result.tool_events, null, 2)}</pre>{result.citations.map((citation) => <button key={citation}>{citation}</button>)}</div></details>
    </section>}
  </div>;
}

function Notebook({ memories }: { memories: any[] }) {
  return <div className="page"><header className="page-header compact"><div><p className="issue">REVIEW NOTEBOOK / 长期记忆</p><h1>What the coach <em>remembers.</em></h1><p>每条记忆都有类型、置信度和复习时间；你始终拥有修改权。</p></div></header><section className="notebook-grid">{memories.length ? memories.map((m, i) => <article className="memory-card" key={m.id}><span>NOTE {String(i+1).padStart(2,"0")} · {m.type}</span><p>{m.content}</p><footer><small>confidence</small><b>{Math.round(m.confidence*100)}%</b><i style={{width:`${m.confidence*100}%`}}/></footer></article>) : <Empty icon={BookOpen} title="No margin notes yet" text="在训练中告诉教练你的岗位或目标，系统只会保存高置信度、可解释的学习信号。" />}</section></div>;
}

function Knowledge({ documents, refresh }: { documents: any[]; refresh: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null); const [busy, setBusy] = useState(false);
  async function upload(file?: File) { if (!file) return; setBusy(true); try { await api.upload(file.name.replace(/\.[^.]+$/, ""), file); refresh(); } finally { setBusy(false); } }
  return <div className="page"><header className="page-header compact"><div><p className="issue">KNOWLEDGE LIBRARY / RAG</p><h1>Sources before <em>answers.</em></h1><p>混合检索、重排、引用溯源；资料是证据，不是系统指令。</p></div><button className="red-button" onClick={() => fileRef.current?.click()}><Upload size={17}/>{busy ? "Indexing…" : "Add source"}</button><input ref={fileRef} hidden type="file" accept=".md,.txt,.pdf" onChange={(e)=>upload(e.target.files?.[0])}/></header><section className="library-table"><div className="table-head"><span>SOURCE</span><span>TYPE</span><span>VERSION</span><span>STATUS</span></div>{documents.map((doc) => <div className="table-row" key={doc.id}><span><FileText size={20}/><b>{doc.title}</b><small>{doc.filename}</small></span><span>{doc.filename.split(".").pop()?.toUpperCase()}</span><span>v{doc.version}</span><span className={`status ${doc.status}`}><i/>{doc.status}</span></div>)}</section><aside className="rag-note"><Database size={24}/><div><b>How retrieval works</b><p>Query Rewrite → metadata filter → lexical + vector search → fusion → rerank → cited answer</p></div></aside></div>;
}

function Evaluation({ evaluations }: { evaluations: any[] }) {
  return <div className="page"><header className="page-header compact"><div><p className="issue">EVALUATION LAB / 质量实验室</p><h1>Improve by evidence,<br/><em>not vibes.</em></h1><p>Golden set、确定性门禁、人工评分与 bad case 在同一个闭环里。</p></div></header><section className="eval-hero"><div><span>RELEASE GATE</span><b>90<sup>%</sup></b><small>minimum pass rate</small></div><ol><li><Check/>Safety cases: must all pass</li><li><Check/>Quality gain: ≥ 3 percentage points</li><li><Check/>Latency regression: ≤ 10%</li><li><Check/>Human approval: required</li></ol></section><section className="eval-list"><div className="section-title"><h2>Evaluation runs</h2><span>{evaluations.length} recorded</span></div>{evaluations.length ? evaluations.map((item) => <article key={item.id}><span className={`status ${item.status}`}><i/>{item.status}</span><b>{item.candidate_version}</b><p>{item.summary?.passed || 0}/{item.summary?.cases || 0} cases passed</p><ChevronRight/></article>) : <Empty icon={ClipboardCheck} title="Evaluator access required" text="使用 admin@example.com 登录后可启动批量评测、盲评结果并审核改进提案。"/>}</section></div>;
}

function Observatory({ lastRun }: { lastRun: string }) {
  const [trace, setTrace] = useState<any>(null);
  useEffect(() => { if (lastRun) api.trace(lastRun).then(setTrace).catch(()=>{}); }, [lastRun]);
  return <div className="page"><header className="page-header compact"><div><p className="issue">RUN OBSERVATORY / 可观测性</p><h1>Every move leaves<br/><em>a trace.</em></h1></div><div className="trace-id">TRACE ID<code>{trace?.run?.trace_id || "Run a practice first"}</code></div></header>{trace ? <><section className="run-stats"><div><span>STATUS</span><b>{trace.run.status}</b></div><div><span>LATENCY</span><b>{trace.run.latency_ms} ms</b></div><div><span>INPUT</span><b>{trace.run.input_tokens} tok</b></div><div><span>OUTPUT</span><b>{trace.run.output_tokens} tok</b></div></section><section className="timeline">{trace.events.map((event:any, i:number)=><article key={event.sequence}><div className="timeline-mark"><span>{String(i+1).padStart(2,"0")}</span></div><div><small>{event.event_type.toUpperCase()}</small><h3>{event.name.replaceAll("_", " ")}</h3><p>{JSON.stringify(event.payload)}</p></div><b>{event.duration_ms} ms</b></article>)}</section></> : <Empty icon={Activity} title="No trace selected" text="完成一次训练后，这里会显示每个 LangGraph 节点、耗时、Token 和工具结果。"/>}</div>;
}

function Empty({ icon: Icon, title, text }: any) { return <div className="empty"><Icon size={34}/><h3>{title}</h3><p>{text}</p></div>; }

export default function App() {
  const [ready, setReady] = useState(Boolean(api.accessToken));
  const [page, setPage] = useState<Page>("today");
  const [user, setUser] = useState<any>(null); const [dashboard, setDashboard] = useState<any>(null);
  const [memories, setMemories] = useState<any[]>([]); const [documents, setDocuments] = useState<any[]>([]);
  const [evaluations, setEvaluations] = useState<any[]>([]); const [lastRun, setLastRun] = useState("");

  function refresh() {
    Promise.all([api.me(), api.dashboard(), api.memories(), api.documents()]).then(([me, dash, mem, docs]) => {
      setUser(me); setDashboard(dash); setMemories(mem); setDocuments(docs);
    }).catch(() => { api.logout(); setReady(false); });
    api.evaluations().then(setEvaluations).catch(() => setEvaluations([]));
  }
  useEffect(() => { if (ready) refresh(); }, [ready]);
  if (!ready) return <Login onReady={() => setReady(true)} />;
  function logout() { api.logout(); setReady(false); }
  return <div className="app-shell"><Sidebar page={page} setPage={setPage} user={user} logout={logout}/><main className="workspace">
    {page === "today" && <Today setPage={setPage} dashboard={dashboard} user={user}/>} {page === "studio" && <Studio onRun={(id)=>{setLastRun(id); refresh();}}/>}
    {page === "notebook" && <Notebook memories={memories}/>} {page === "knowledge" && <Knowledge documents={documents} refresh={refresh}/>} {page === "evaluation" && <Evaluation evaluations={evaluations}/>} {page === "observatory" && <Observatory lastRun={lastRun}/>} </main></div>;
}
