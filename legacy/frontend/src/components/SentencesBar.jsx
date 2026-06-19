import React from 'react';

export default function SentencesBar({ state }) {
  if(!state) return null;
  return (
    <div className="sentences" dangerouslySetInnerHTML={{__html: state.sentences_window_html}} />
  );
}
