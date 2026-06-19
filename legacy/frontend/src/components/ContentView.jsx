import React from 'react';

export default function ContentView({ state, wrapperRef }) {
  if(!state) return null;
  return (
    <div className="prev-next-wrapper" ref={wrapperRef}>
      <div className="html-block" dangerouslySetInnerHTML={{__html: state.prev_html}} />
      <div id="scroll_here"></div>
      <div className="html-block" dangerouslySetInnerHTML={{__html: state.html_content}} />
      <div className="html-block" dangerouslySetInnerHTML={{__html: state.next_html}} />
    </div>
  );
}
