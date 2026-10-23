import React from 'react';
const paths:Record<string,React.ReactNode>={
 activity:<path d="M2 12h4l3-8 6 16 3-8h4"/>,
 heart:<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>,
 patients:<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.9"/><circle cx="9" cy="7" r="4"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/></>,
 alert:<><path d="m12 3 10 18H2L12 3Z"/><path d="M12 9v4m0 4h.01"/></>,
 check:<path d="m5 12 4 4L19 6"/>,unknown:<><circle cx="12" cy="12" r="9"/><path d="M12 11v5m0-9h.01"/></>,
 drop:<path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13Z"/>,
 temp:<><path d="M9 14.8V5a3 3 0 0 1 6 0v9.8a5 5 0 1 1-6 0Z"/><path d="M12 9v10"/></>,
 shield:<><path d="m12 3 9 4v6c0 5-9 9-9 9s-9-4-9-9V7l9-4Z"/><path d="m8 12 3 3 5-6"/></>,
 settings:<><path d="M3 6h18M3 12h18M3 18h18"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="9" cy="18" r="2"/></>,
 arrow:<path d="m9 5 7 7-7 7"/>,refresh:<><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6 6a8 8 0 0 1 13 2M5 16a8 8 0 0 0 13 2"/></>,
 sun:<><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/></>,
 moon:<path d="M21 13A9 9 0 0 1 11 3a9 9 0 1 0 10 10Z"/>,
 logout:<><path d="M9 3H4v18h5m6-14 5 5-5 5m-7-5h12"/></>,
 lcd:<><rect x="2" y="4" width="20" height="14" rx="2"/><path d="M8 22h8m-4-4v4M6 9h12M6 13h10"/></>,
 search:<><circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/></>,
};
export function Icon({name,size=20}:{name:string;size?:number}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]??paths.unknown}</svg>;}
