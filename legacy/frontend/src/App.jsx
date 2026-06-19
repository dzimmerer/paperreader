import React, { useEffect, useRef, useState } from 'react';
import { getState, control, fetchAudioBlob } from './api.js';
import Controls from './components/Controls.jsx';
import SpeedControls from './components/SpeedControls.jsx';
import ContentView from './components/ContentView.jsx';
import FigureView from './components/FigureView.jsx';
import SentencesBar from './components/SentencesBar.jsx';

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [urlInput, setUrlInput] = useState('https://arxiv.org/abs/2505.10562');
  const [state, setState] = useState(null);
  const [scrollLocked, setScrollLocked] = useState(true); // true = auto-follow
  const audioRef = useRef(null);
  const playingRef = useRef(false);
  const lastAudioKey = useRef('');
  const prevSentenceKeyRef = useRef('');
  const contentWrapperRef = useRef(null);

  // Create session
  async function startSession(e) {
    e.preventDefault();
    // Navigate to a shareable GET-based reading page
    const target = `/read?url=${encodeURIComponent(urlInput.trim())}`;
    // Use pushState to avoid full reload (still triggers effect) and remain SPA; fallback reload if needed
    window.history.pushState({}, '', target);
    // Trigger session creation effect manually (will detect new query param)
    triggerSessionFromQuery();
  }

  // Helper to parse query param and create a session via GET endpoint
  const triggerSessionFromQuery = async () => {
    const params = new URLSearchParams(window.location.search);
    const urlParam = params.get('url');
    if(!urlParam) return;
    if(sessionId) return; // already have session
    try {
      const r = await fetch(`/api/session?url=${encodeURIComponent(urlParam)}`);
      if(!r.ok) throw new Error('Failed to create session');
      const data = await r.json();
      setSessionId(data.session_id);
      setUrlInput(urlParam);
    } catch(err) {
      // eslint-disable-next-line no-console
      console.error('Session creation error', err);
    }
  };

  // On initial mount or when path changes (user manual navigation / back button), try to create session
  useEffect(() => {
    triggerSessionFromQuery();
    // Listen to popstate for back/forward navigation
    const handler = () => triggerSessionFromQuery();
    window.addEventListener('popstate', handler);
    return () => window.removeEventListener('popstate', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll state
  useEffect(() => {
    if(!sessionId) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const st = await getState(sessionId);
        if(!cancelled) setState(st);
      } catch(e) {
        // eslint-disable-next-line no-console
        console.warn('poll error', e);
      } finally {
        if(!cancelled) setTimeout(poll, 300);
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [sessionId]);

  // Playback logic
  useEffect(() => {
    if(!state || state.end) return;
    const shouldPlay = state.play_state === 'PLAY';
    const currentKey = `${state.div_idx}:${state.sentence_idx}`;

    async function ensureAudio() {
      if(!shouldPlay) return;
      if(currentKey === lastAudioKey.current && playingRef.current) return; // already playing
      try {
        const blob = await fetchAudioBlob(sessionId, state.div_idx, state.sentence_idx);
        const url = URL.createObjectURL(blob);
        if(audioRef.current) {
          audioRef.current.src = url;
          audioRef.current.play().catch(()=>{});
          playingRef.current = true;
          lastAudioKey.current = currentKey;
        }
      } catch(e) {
        // audio not yet ready; retry shortly
        setTimeout(ensureAudio, 400);
      }
    }
    ensureAudio();
  }, [state, sessionId]);

  function onEnded() {
    playingRef.current = false;
    if(state && state.play_state === 'PLAY') {
      control(sessionId, 'next_sentence').catch(()=>{});
    }
  }

  async function onAction(action) {
    if(action === 'toggle_scroll') { setScrollLocked(l => !l); return; }
    await control(sessionId, action);
  }

  // Auto scroll when locked and sentence changes
  useEffect(() => {
    if(!state || !scrollLocked) return;
    const currentKey = `${state.div_idx}:${state.sentence_idx}`;
    if(prevSentenceKeyRef.current === currentKey) return;
    prevSentenceKeyRef.current = currentKey;
    // Attempt to find bolded sentence inside the current html block and scroll to its approximate position
    // We wrap current html_content in its own block already; scroll that block into view.
    if(contentWrapperRef.current) {
      // The second html-block corresponds to current content (prev, scroll_here anchor, current, next)
      const blocks = contentWrapperRef.current.querySelectorAll('.html-block');
      if(blocks.length >= 2) {
        const currentBlock = blocks[1];
        currentBlock.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }, [state, scrollLocked]);

  return (
    <div style={{height:'100vh', display:'flex', flexDirection:'column'}}>
      {!sessionId && (
        <form onSubmit={startSession} style={{padding:10}}>
          <input style={{width:'40rem'}} value={urlInput} onChange={e=>setUrlInput(e.target.value)} />
          <button type="submit">Start</button>
        </form>
      )}
      {sessionId && state && (
        <>
          <div style={{padding:'10px', height:'10vh', overflow:'hidden'}}>
            <h4 className={state.is_title ? 'sec-title-highlight' : ''}>{state.sec_title}</h4>
          </div>
          <div className="layout">
            <div className="left-pane">
              <ContentView state={state} wrapperRef={contentWrapperRef} />
            </div>
            <div className="right-pane">
              <FigureView state={state} />
            </div>
          </div>
          <div className="bottom-bar">
            <SentencesBar state={state} />
          </div>
          <Controls state={state} onAction={onAction} scrollLocked={scrollLocked} />
          <SpeedControls state={state} onAction={onAction} />
          <audio ref={audioRef} onEnded={onEnded} />
        </>
      )}
    </div>
  );
}
