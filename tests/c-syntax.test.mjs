// SPDX-License-Identifier: GPL-2.0-only
import test from 'node:test';
import assert from 'node:assert/strict';
import {formatCArgument,formatCDeclaration} from '../public/c-syntax.mjs';
const plain=html=>html.replace(/<\/?span(?: class="c-[a-z]+")?>/g,'').replace(/&(amp|lt|gt|quot|#39);/g,(_,key)=>({amp:'&',lt:'<',gt:'>',quot:'"','#39':"'"}[key]));

test('syntax colours preserve exact declarations, pointers, arrays and callbacks',()=>{
  for(const declaration of [
    'asmlinkage ssize_t sys_read(unsigned int fd, char __user *buf, size_t count);',
    'long sys_map(void (*callback)(int, void *), unsigned int fds[SIZE]);',
    'asmlinkage long sys_getpid(void);',
  ]) assert.equal(plain(formatCDeclaration(declaration)),declaration);
  assert.match(formatCArgument('char __user *buf'),/class="c-name">buf<\/span>/);
  assert.match(formatCArgument('unsigned int fds[SIZE]'),/class="c-name">fds<\/span>/);
  assert.match(formatCArgument('void (*callback)(int, void *)'),/class="c-name">callback<\/span>/);
  assert.doesNotMatch(formatCArgument('unsigned long'),/c-name/);
});

test('untrusted declaration text remains escaped text',()=>{
  const text='char *name[<img src=x onerror="bad()">] & other';
  const html=formatCArgument(text);
  assert.doesNotMatch(html,/<img|onerror="/);
  assert.equal(plain(html),text);
});
