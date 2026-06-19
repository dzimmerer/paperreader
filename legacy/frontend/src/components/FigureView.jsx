import React from 'react';

export default function FigureView({ state }) {
  if(!state) return null;
  return (
    <div className="figure-scale" dangerouslySetInnerHTML={{__html: state.figure_html}} />
  );
}
