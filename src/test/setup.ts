import '@testing-library/jest-dom/vitest';
import {afterEach,beforeEach,vi} from 'vitest';
import {cleanup} from '@testing-library/react';
beforeEach(()=>{if(typeof document!=='undefined'){localStorage.clear();document.documentElement.dataset.theme='light';}});
afterEach(()=>{cleanup();vi.restoreAllMocks();});
// jsdom has no native modal implementation; this is only a component-test substitute.
if(typeof HTMLDialogElement!=='undefined'){
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
}

if(typeof window!=="undefined") Object.defineProperty(window,"scrollTo",{value:vi.fn(),writable:true});
