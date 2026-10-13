import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
const exports={};
const compiled=ts.transpileModule(fs.readFileSync(new URL('../components/SocialDraftMedia.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.React}}).outputText;
vm.runInNewContext(compiled,{exports,React});
const render=props=>renderToStaticMarkup(React.createElement(exports.default,{id:'private-id',headline:'Reviewed headline',assets:[],...props}));
const assets=[0,1].map(index=>({index,mimeType:'image/png',width:1122,height:1402}));
test('single image retains its existing private preview',()=>{
 const html=render({format:'image'});assert.match(html,/private-id\/image/);assert.doesNotMatch(html,/<video/);
});
test('carousel renders every slide in reviewed order without external URLs',()=>{
 const html=render({format:'carousel',assets});
 assert.ok(html.indexOf('/media/0')<html.indexOf('/media/1'));
 assert.match(html,/Slide 1 of 2/);assert.match(html,/Slide 2 of 2/);
 assert.doesNotMatch(html,/https?:|\/image"/);
});
test('reel uses controls, private bytes and no autoplay',()=>{
 const html=render({format:'reel',assets:[{...assets[0],mimeType:'video/mp4'}]});
 assert.match(html,/<video[^>]*controls/);assert.match(html,/preload="metadata"/);
 assert.match(html,/\/media\/0/);assert.doesNotMatch(html,/autoplay/i);
});
test('missing, gapped, wrong-ratio and wrong-MIME packages never use placeholders',()=>{
 for(const props of [{format:'carousel',assets:[]},{format:'carousel',assets:assets.toReversed()},{format:'carousel',assets:[assets[0],{...assets[1],width:1123}]},{format:'reel',assets:[assets[0]]}]){
  const html=render(props);assert.match(html,/Approval is unavailable/);assert.doesNotMatch(html,/<img|<video/);
 }
});
test('approval route refuses non-image approval even when called outside the UI',()=>{
 const source=fs.readFileSync(new URL('../app/api/social-drafts/[id]/review/route.ts',import.meta.url),'utf8');
 assert.match(source,/AND \(NOT \$6 OR media_format='image'\)/);
});
