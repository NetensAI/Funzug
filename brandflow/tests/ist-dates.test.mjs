import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import * as dates from '../lib/ist-dates.mjs';
const require=createRequire(import.meta.url);

test('day first input preserves ambiguous dates and rejects impossible calendar dates',()=>{
 assert.equal(dates.parseDisplayDate('05/11/2026'),'2026-11-05');
 assert.equal(dates.parseDisplayDate('11/05/2026'),'2026-05-11');
 assert.equal(dates.parseDisplayDate('29/02/2028'),'2028-02-29');
 for(const bad of ['29/02/2026','31/04/2026','19/13/2026','2026-10-19','1/2/2026','00/10/2026'])assert.equal(dates.parseDisplayDate(bad),null);
 assert.equal(dates.localSchedule('05/11/2026','18:45')+':00+05:30','2026-11-05T18:45:00+05:30');
 assert.equal(dates.localSchedule('31/02/2026','18:45'),'');
});
test('IST day rollover and midnight format independently of machine locale',()=>{
 assert.equal(dates.toIstLocalValue('2026-10-19T18:30:00Z'),'2026-10-20T00:00');
 assert.equal(dates.formatIstDateTime('2026-11-05T13:15:00Z'),'05/11/2026 18:45');
 assert.equal(dates.formatIstDateTime(null),'');
});
test('schedule field visibly renders DD/MM/YYYY and preserves calendar and time selection',()=>{
 const module={exports:{}};
 const compiled=ts.transpileModule(fs.readFileSync(new URL('../components/IstScheduleInput.tsx',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(compiled,{module,exports:module.exports,require:name=>name==='@/lib/ist-dates.mjs'?dates:require(name)});
 const html=renderToStaticMarkup(React.createElement(module.exports.default,{label:'Schedule (IST)',value:'2026-11-05T18:45',onChange:()=>{}}));
 assert.match(html,/type="text"[^>]*placeholder="DD\/MM\/YYYY"[^>]*value="05\/11\/2026"/);
 assert.match(html,/Choose date from calendar/);assert.match(html,/type="time"/);assert.match(html,/18:45/);
 assert.doesNotMatch(html,/type="datetime-local"/);
});
