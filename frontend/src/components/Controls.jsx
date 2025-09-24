import React from 'react';

export default function Controls({ state, onAction, scrollLocked }) {
  if(!state) return null;
  return (
    <div className="controls">
      <div style={{background:'#fff', width:'2rem', textAlign:'center'}}>{state.div_idx}</div>
      <div style={{background:'#fff', width:'2rem', textAlign:'center'}}>{state.sentence_idx}</div>
      <button onClick={() => onAction('prev_div')}>&lt;&lt;</button>
      <button onClick={() => onAction('prev_sentence')}>&lt;</button>
      <button onClick={() => onAction('play_pause')}>{state.play_state === 'PLAY' ? 'pause' : 'play'}</button>
      <button onClick={() => onAction('next_sentence')}>&gt;</button>
      <button onClick={() => onAction('next_div')}>&gt;&gt;</button>
      <button title={scrollLocked ? 'Unlock scrolling' : 'Lock scrolling'} onClick={() => onAction('toggle_scroll')}>
        {scrollLocked ? '🔒' : '🔓'}
      </button>
    </div>
  );
}
