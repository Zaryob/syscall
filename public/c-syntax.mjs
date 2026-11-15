// SPDX-License-Identifier: GPL-2.0-only
// Presentation only: preserve the exact declaration for reading and copying.
const escape = text => text.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const qualifiers = new Set(['const','volatile','restrict','asmlinkage','register']);
const types = new Set(['void','char','short','int','long','signed','unsigned','float','double','struct','union','enum','bool']);

function nameRange(source) {
  const pointer = /\(\s*\*\s*([A-Za-z_]\w*)\s*\)/.exec(source);
  if (pointer) {
    const start = pointer.index + pointer[0].indexOf(pointer[1]);
    return [start,start+pointer[1].length];
  }
  const words = [...source.replace(/\[[^\]]*\]/g, '').matchAll(/[A-Za-z_]\w*/g)];
  const last = words.at(-1);
  if (!last || words.length < 2 || types.has(last[0]) || qualifiers.has(last[0]) || /^__/.test(last[0])) return;
  if (['struct','union','enum'].includes(words.at(-2)?.[0])) return;
  return [last.index,last.index+last[0].length];
}

function colour(source, name, call = false) {
  return [...source.matchAll(/[A-Za-z_]\w*|\*|[^A-Za-z_*]+/g)].map(match => {
    const token=match[0], text=escape(token);
    let role;
    if (name && match.index===name[0] && match.index+token.length===name[1]) role=call?'call':'name';
    else if (token==='*') role='pointer';
    else if (/^[A-Za-z_]\w*$/.test(token)) role=qualifiers.has(token)||/^__/.test(token)?'qualifier':(types.has(token)||!name||match.index<name[0]||/_t$/.test(token)?'type':undefined);
    return role?`<span class="c-${role}">${text}</span>`:text;
  }).join('');
}

export const formatCArgument = source => colour(source,nameRange(source));

export function formatCDeclaration(source) {
  const opening=source.indexOf('('), closing=source.lastIndexOf(')');
  if (opening<0 || closing<opening) return colour(source);
  const prefix=source.slice(0,opening), name=[...prefix.matchAll(/[A-Za-z_]\w*/g)].at(-1);
  let output=colour(prefix,name&&[name.index,name.index+name[0].length],true)+'(';
  const parameters=source.slice(opening+1,closing);
  let start=0,depth=0;
  for(let i=0;i<parameters.length;i++) {
    if(parameters[i]==='(' || parameters[i]==='[') depth++;
    if(parameters[i]===')' || parameters[i]===']') depth--;
    if(parameters[i]===',' && depth===0) {
      output+=formatCArgument(parameters.slice(start,i))+',';
      start=i+1;
    }
  }
  return output+formatCArgument(parameters.slice(start))+escape(source.slice(closing));
}
