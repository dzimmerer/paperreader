import React from 'react';

export default function SpeedControls({ state, onAction }) {
  if(!state) return null;
  return (
    <div className="speed-controls">
      <button onClick={() => onAction('speed_dec')}>-</button>
      <button onClick={() => onAction('speed_inc')}>+</button>
      <div style={{background:'#fff', width:'2rem', textAlign:'center'}}>{state.speed?.toFixed ? state.speed.toFixed(1) : state.speed}</div>
    </div>
  );
}
